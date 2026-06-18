# src/bugbot/core/strategy_smc.py
"""
BugBot v2.0 — SMC Strategy Engine para MNQ/MES/MGC
Reemplaza la lógica EMA21/50 + VWAP (demasiado restrictiva, 0 señales)
por estructura real: CHoCH / BOS + sweep de liquidez, con MACD como filtro de momentum.

Diseño:
  - swing highs/lows fractales (pivotes) → estructura del mercado
  - BOS  = ruptura de estructura en la dirección de la tendencia
  - CHoCH = ruptura del último swing contrario (cambio de carácter / giro)
  - liquidity sweep = la vela barre un swing previo y cierra de vuelta (stop hunt)
  - MACD = confirma momentum en la dirección del setup

Cada función de descarte devuelve un motivo legible para que el engine lo loggee.
Entrada al cierre de la vela de confirmación; SL detrás del sweep/swing estructural.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import pytz

# ─── Filtro de sesiones (igual que v2, centralizado aquí) ─────────────────────

SESSIONS = {
    "NY":           {"symbols": ["MNQ", "MES"], "tz": "America/Denver", "start": 7,  "end": 11},
    "NY_AFTERNOON": {"symbols": ["MNQ", "MES"], "tz": "America/Denver", "start": 12, "end": 15},
    "ASIA":         {"symbols": ["MGC"],        "tz": "America/Denver", "start": 18, "end": 23},
}

def active_session(symbol: str) -> str | None:
    """Devuelve el nombre de la sesión activa para el símbolo, o None."""
    now_utc = datetime.now(timezone.utc)
    for name, cfg in SESSIONS.items():
        if symbol.upper() not in cfg["symbols"]:
            continue
        now = now_utc.astimezone(pytz.timezone(cfg["tz"]))
        if cfg["start"] <= now.hour < cfg["end"]:
            return name
    return None

# ─── Indicadores ──────────────────────────────────────────────────────────────

def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["macd"]      = ema_fast - ema_slow
    df["macd_sig"]  = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_sig"]
    return df

def find_pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    """
    Pivotes fractales: un swing high es un high mayor que `left` velas a la
    izquierda y `right` a la derecha (idem low). Confirmados (no repintan):
    sólo marcamos pivotes que ya tienen `right` velas posteriores.
    """
    highs = df["high"].values
    lows  = df["low"].values
    n     = len(df)
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for i in range(left, n - right):
        win_h = highs[i - left : i + right + 1]
        win_l = lows[i - left : i + right + 1]
        if highs[i] == win_h.max() and (win_h == highs[i]).sum() == 1:
            sh[i] = highs[i]
        if lows[i] == win_l.min() and (win_l == lows[i]).sum() == 1:
            sl[i] = lows[i]
    df["pivot_high"] = sh
    df["pivot_low"]  = sl
    return df

# ─── Estructura de mercado ────────────────────────────────────────────────────

def _last_two(series: pd.Series) -> list[tuple[int, float]]:
    """Devuelve [(idx_posicional, valor)] de los 2 últimos pivotes no-NaN."""
    vals = series.dropna()
    out = []
    for pos in vals.index[-2:]:
        out.append((series.index.get_loc(pos), float(vals.loc[pos])))
    return out

def market_structure(df: pd.DataFrame) -> dict:
    """
    Determina bias por secuencia de pivotes:
      HH + HL → alcista ; LH + LL → bajista ; mixto → rango/neutral
    Devuelve el último swing high y low confirmados (niveles de liquidez).
    """
    phs = _last_two(df["pivot_high"])
    pls = _last_two(df["pivot_low"])

    bias = "NEUTRAL"
    if len(phs) == 2 and len(pls) == 2:
        higher_high = phs[1][1] > phs[0][1]
        higher_low  = pls[1][1] > pls[0][1]
        lower_high  = phs[1][1] < phs[0][1]
        lower_low   = pls[1][1] < pls[0][1]
        if higher_high and higher_low:
            bias = "LONG"
        elif lower_high and lower_low:
            bias = "SHORT"

    return {
        "bias":           bias,
        "last_swing_high": phs[-1][1] if phs else None,
        "last_swing_low":  pls[-1][1] if pls else None,
        "prev_swing_high": phs[0][1] if len(phs) == 2 else None,
        "prev_swing_low":  pls[0][1] if len(pls) == 2 else None,
    }

# ─── Detección de eventos SMC ─────────────────────────────────────────────────

def _macd_ok(last, side: str) -> bool:
    if side == "LONG":
        return last["macd_hist"] > 0 and last["macd"] > last["macd_sig"]
    return last["macd_hist"] < 0 and last["macd"] < last["macd_sig"]

def detect_signal(df: pd.DataFrame, left: int = 3, right: int = 3) -> dict:
    """
    Detecta setup SMC sobre la última vela CERRADA.

    Devuelve SIEMPRE un dict con clave "ok" (bool) y "reason" (str).
    Si ok=True incluye: side, entry, sl, zona, bias, event.

    Lógica:
      1. sesión activa (si hay símbolo en attrs)
      2. estructura → bias
      3. liquidity sweep del último swing contrario + cierre de vuelta (stop hunt)
         o BOS/CHoCH confirmado por cierre más allá del swing
      4. MACD confirma momentum
    """
    symbol = df.attrs.get("symbol", "")
    if len(df) < 60:
        return {"ok": False, "reason": f"datos insuficientes ({len(df)} velas)"}

    if symbol:
        sess = active_session(symbol)
        if sess is None:
            return {"ok": False, "reason": "fuera de sesión"}
    else:
        sess = None

    df = add_macd(df)
    df = find_pivots(df, left, right)
    ms = market_structure(df)
    bias = ms["bias"]

    if bias == "NEUTRAL":
        return {"ok": False, "reason": "estructura en rango (sin HH/HL ni LH/LL)"}

    last = df.iloc[-1]
    sw_high = ms["last_swing_high"]
    sw_low  = ms["last_swing_low"]
    if sw_high is None or sw_low is None:
        return {"ok": False, "reason": "sin swings confirmados"}

    high, low, close, open_ = last["high"], last["low"], last["close"], last["open"]

    # ── LONG: sweep de liquidez bajo el último swing low + cierre de vuelta ──
    if bias == "LONG":
        swept = low < sw_low and close > sw_low          # barre y recupera
        bos   = close > sw_high                            # rompe estructura al alza
        if not (swept or bos):
            return {"ok": False, "reason": "sin sweep bajo swing low ni BOS alcista"}
        if not _macd_ok(last, "LONG"):
            return {"ok": False, "reason": "MACD no confirma LONG"}
        if close <= open_:
            return {"ok": False, "reason": "vela de confirmación no alcista"}
        event = "BOS" if bos else "SWEEP"
        sl = min(low, sw_low) - (close * 0.0004)
        return {
            "ok": True, "reason": "", "side": "LONG",
            "entry": float(round(close, 2)), "sl": float(round(sl, 2)),
            "zona": event, "event": event, "bias": bias, "session": sess,
        }

    # ── SHORT: sweep sobre el último swing high + cierre de vuelta ──
    if bias == "SHORT":
        swept = high > sw_high and close < sw_high
        bos   = close < sw_low
        if not (swept or bos):
            return {"ok": False, "reason": "sin sweep sobre swing high ni BOS bajista"}
        if not _macd_ok(last, "SHORT"):
            return {"ok": False, "reason": "MACD no confirma SHORT"}
        if close >= open_:
            return {"ok": False, "reason": "vela de confirmación no bajista"}
        event = "BOS" if bos else "SWEEP"
        sl = max(high, sw_high) + (close * 0.0004)
        return {
            "ok": True, "reason": "", "side": "SHORT",
            "entry": float(round(close, 2)), "sl": float(round(sl, 2)),
            "zona": event, "event": event, "bias": bias, "session": sess,
        }

    return {"ok": False, "reason": "sin condición de entrada"}
