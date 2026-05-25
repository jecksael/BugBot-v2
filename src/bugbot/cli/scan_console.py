from __future__ import annotations

from typing import Dict, List
import math
import pandas as pd

from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..adapters.exchange import ExchangeRouter

# Lógica básica
from ..core.strategy import ema_cross_signal

# Indicadores
from ..core.indicators import add_ema
from ..core.indicators import add_indicators_15m, add_indicators_4h  # ajusta si tienes variantes por TF

# Estrategias avanzadas existentes
from ..strategies.advanced import (
    find_signals_sniper_15m,
    find_signals_gato_15m,
)

# Motor de reglas (ruta según tu proyecto actual)
from ..core.rules_engine import load_rules, eval_long_rule, eval_short_rule
from ..core.metrics import bump_signal, bump_reason, snapshot
from ..core.store import init_db, save_signal
# ------------------ utilidades locales ------------------

def _fmt(x: float) -> str:
    s = f"{x:,.2f}"
    return s.rstrip("0").rstrip(".")


def _build_plan_atr(entry: float, side: str, atr_value: float, k_atr: float, tp_r: list[float]):
    """
    Plan ATR-based:
      R = k_atr * ATR
      SL = entry -/+ R
      TP_i = entry + sign * (R * tp_r[i])
    """
    side_up = side.upper() == "LONG"
    R = float(k_atr) * float(atr_value)
    sl = entry - R if side_up else entry + R
    tps = [(entry + (R * r)) if side_up else (entry - (R * r)) for r in tp_r]
    return tps, sl, R


def _calc_qty_by_risk(entry: float, sl: float, equity: float, risk_pct: float):
    """
    Tamaño aproximado (spot o nocional):
      riesgo$ = equity * risk_pct
      R$ por unidad = |entry - SL|
      qty = riesgo$ / R$
    """
    risk_dollars = float(equity) * float(risk_pct)
    r_per_unit = abs(entry - sl)
    if r_per_unit <= 0:
        return 0.0
    return risk_dollars / r_per_unit


def _print_adv_signals(signals) -> int:
    """Imprime señales avanzadas y devuelve cuántas imprimió."""
    count = 0
    if not signals:
        return count
    for s in signals:
        print(f"[{s.exchange}] {s.symbol} | {s.rule} {s.side} ✅ score={s.score}")
        print(
            "  "
            + f"entry={_fmt(s.entry)}  sl={_fmt(s.sl)}  "
            + f"tp={', '.join(_fmt(x) for x in s.tp)}  R={_fmt(s.R)}"
        )
        if s.reasons:
            print(f"  reasons: {', '.join(s.reasons)}")
        count += 1
    return count


def _ensure_ema_cols(df, fast: int, slow: int):
    """Asegura ema{fast}/ema{slow} en el DF."""
    ef, es = f"ema{fast}", f"ema{slow}"
    if ef not in df.columns:
        df = add_ema(df, fast)
    if es not in df.columns:
        df = add_ema(df, slow)
    return df


def _ensure_atr(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asegura ATR14. Si no existe, lo calcula:
      TR = max(high-low, |high-prev_close|, |low-prev_close|)
      ATR14 = media móvil simple de TR (14)
    """
    if "atr14" not in df.columns:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr1 = (high - low).abs()
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr14"] = tr.rolling(14).mean()
    return df


def _ensure_quality_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asegura columnas usadas por checks:
      - ema21/ema52 (se asume que ya vienen antes)
      - atr14 y atr_pct = atr14/close*100
      - gap_2152_pct = |ema21-ema52|/close*100
      - vol_sma20 si existe volume
    """
    df = _ensure_atr(df)
    if "atr_pct" not in df.columns:
        df["atr_pct"] = df["atr14"] / df["close"] * 100.0

    if "gap_2152_pct" not in df.columns and all(c in df.columns for c in ("ema21", "ema52")):
        df["gap_2152_pct"] = (df["ema21"] - df["ema52"]).abs() / df["close"] * 100.0

    if "vol_sma20" not in df.columns and "volume" in df.columns:
        df["vol_sma20"] = df["volume"].rolling(20).mean()

    return df


# ------------------ programa principal ------------------

def main() -> None:
    init_db()
    s = get_settings()
    setup_logging(s.log_level)

    print(f"\n=== BUGBot scan (console) ===")
    print(f"TF: {s.timeframe} | EMAs: {s.ema_fast}/{s.ema_slow}")
    print(f"Exchanges (failover): {', '.join(s.exchanges)}")
    print(f"Symbols: {', '.join(s.symbols)}\n")

    router = ExchangeRouter.from_env()
    total_signals = 0

    # Carga de reglas (una vez)
    cfg = load_rules(getattr(s, "rules_path", None))

    # Sizing por ATR (defaults por si no están en settings)
    k_atr = getattr(s, "atr_k_sl", 1.5)                 # SL = k * ATR
    tp_r  = getattr(s, "tp_r", [1.0, 2.0, 3.0])         # TPs por R
    equity   = getattr(s, "equity", None)               # para qty opcional
    risk_pct = getattr(s, "risk_pct", 0.01)

    for symbol in s.symbols:
        try:
            # --------- BLOQUE BÁSICO (cruce EMAs) ----------
            ex_id, df = router.fetch_ohlcv_df(symbol, timeframe=s.timeframe, limit=200)
            df = _ensure_ema_cols(df, s.ema_fast, s.ema_slow)

            sig = ema_cross_signal(df, s.ema_fast, s.ema_slow)
            last = df.iloc[-1]
            ef, es = f"ema{s.ema_fast}", f"ema{s.ema_slow}"

            if sig:
                # Para coherencia, usamos ATR y entry desde 1H
                _, df1h_for_basic = router.fetch_ohlcv_df(symbol, timeframe="1H", limit=320)
                for p in (21, 52):
                    df1h_for_basic = add_ema(df1h_for_basic, p)
                df1h_for_basic = _ensure_quality_cols(df1h_for_basic)

                row1h_b = df1h_for_basic.iloc[-1]
                entry_b = float(row1h_b.get("ema21", row1h_b["close"]))
                atr14_b = float(row1h_b.get("atr14", 0.0))

                tps_b, sl_b, R_b = _build_plan_atr(entry_b, sig["side"], atr14_b, k_atr, tp_r)
                qty_b = _calc_qty_by_risk(entry_b, sl_b, equity, risk_pct) if (equity and atr14_b > 0) else None

                total_signals += 1
                print(f"[{ex_id}] {symbol} → {sig['side']}")
                print(
                    f"  entry={_fmt(entry_b)} | SL={_fmt(sl_b)} | "
                    + " | ".join([f"TP{i+1}={_fmt(tp)}" for i, tp in enumerate(tps_b)])
                    + f" | R={_fmt(R_b)}"
                    + (f" | qty≈{_fmt(qty_b)}" if qty_b else "")
                )
                save_signal({
                    "exchange": ex_id,
                    "symbol": symbol,
                    "side": side,                 # "LONG"/"SHORT"
                    "rule": cfg.get("rules",{}).get("meta",{}).get("rules_version","v1.1-atr"),
                    "score": score if 'score' in locals() else 0,
                    "entry": entry,
                    "sl": sl,
                    "tp": tps,
                    "R": R,                       # si es la básica y usaste ATR plan, pasa R_b
                    "reasons": []
                })
            else:
                print(f"[{ex_id}] {symbol} → sin cruce")
                print(
                    f"  close={_fmt(float(last['close']))} | "
                    f"{ef}={_fmt(float(last[ef]))} | "
                    f"{es}={_fmt(float(last[es]))}"
                )

            # --------- BLOQUE MOTOR DE REGLAS (LONG/SHORT) ----------
            try:
                # Descarga multi-TF
                _, df15 = router.fetch_ohlcv_df(symbol, timeframe="15m", limit=320)
                _, df1h = router.fetch_ohlcv_df(symbol, timeframe="1H",  limit=320)
                _, df4h = router.fetch_ohlcv_df(symbol, timeframe="4H",  limit=220)
                _, dfw  = router.fetch_ohlcv_df(symbol, timeframe="1W",  limit=220)

                # EMAs base por TF (mínimo 21/52)
                for p in (21, 52):
                    df15 = add_ema(df15, p)
                    df1h = add_ema(df1h, p)
                    df4h = add_ema(df4h, p)
                    dfw  = add_ema(dfw,  p)

                # Indicadores (y columnas de calidad)
                df15 = add_indicators_15m(df15)
                df4h = add_indicators_4h(df4h)
                df1h = _ensure_quality_cols(df1h)
                df4h = _ensure_quality_cols(df4h)

                data: Dict[str, pd.DataFrame] = {"15M": df15, "1H": df1h, "4H": df4h, "1W": dfw}

                res_long = eval_long_rule(data, cfg)
                res_short = eval_short_rule(data, cfg)

                if res_long.passed or res_short.passed:
                    side = "LONG" if res_long.passed and res_long.score >= res_short.score else "SHORT"
                    score = res_long.score if side == "LONG" else res_short.score

                    # Entry y ATR desde 1H (consistente con checks)
                    row1h = df1h.iloc[-1]
                    entry = float(row1h.get("ema21", row1h["close"]))
                    atr14 = float(row1h.get("atr14", 0.0))

                    tps, sl, R = _build_plan_atr(entry, side, atr14, k_atr, tp_r)
                    qty = _calc_qty_by_risk(entry, sl, equity, risk_pct) if (equity and atr14 > 0) else None

                    total_signals += 1
                    print(f"[{ex_id}] {symbol} ✅ Motor reglas → {side} | score={score}")
                    print(
                        f"  entry={_fmt(entry)} | SL={_fmt(sl)} | "
                        + " | ".join([f"TP{i+1}={_fmt(tp)}" for i, tp in enumerate(tps)])
                        + f" | R={_fmt(R)}"
                        + (f" | qty≈{_fmt(qty)}" if qty else "")
                    )

                else:
                    # Mostrar el “por qué no” más relevante
                    top = res_long if res_long.score >= res_short.score else res_short
                    if top.reasons:
                        print("  (rules) sin señal • razones:", ", ".join(top.reasons))

            except Exception as rules_err:
                print(f"  [rules] {symbol}: {rules_err}")

            # --------- BLOQUE AVANZADO (Sniper + Gato) ----------
            try:
                ex_id15, df15b = router.fetch_ohlcv_df(symbol, timeframe="15m", limit=320)
                _, df4hb = router.fetch_ohlcv_df(symbol, timeframe="4H",  limit=220)

                for p in (21, 52, 100):
                    df15b = add_ema(df15b, p)
                    df4hb = add_ema(df4hb, p)

                df15b = add_indicators_15m(df15b)
                df4hb = add_indicators_4h(df4hb)

                adv_signals = []
                adv_signals += find_signals_sniper_15m(ex_id15, symbol, df15b, df4hb)
                adv_signals += find_signals_gato_15m(ex_id15, symbol, df15b, df4hb)

                total_signals += _print_adv_signals(adv_signals)

            except Exception as adv_err:
                print(f"  [adv] {symbol}: {adv_err}")

        except Exception as e:
            print(f"[{symbol}] error: {e}")
    print("Métricas:", snapshot())
    print(f"\nResumen: {total_signals} señales.\n")


if __name__ == "__main__":
    main()
