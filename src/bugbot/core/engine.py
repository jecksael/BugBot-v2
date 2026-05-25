from __future__ import annotations
from datetime import datetime, timezone
from . import formatting as fmt
from .indicators import add_ema
from .strategy import ema_fractal_signal
from ..config.settings import get_settings
from ..adapters.exchange import ExchangeRouter

def _build_tps_sl(
    entry: float,
    side: str,
    tp_pcts: list[float],
    sl_pct: float,
    *,
    sl_hint: float | None = None,
):
    mult = 1 if side == "LONG" else -1
    tps = [entry * (1 + mult*p) for p in tp_pcts]
    if sl_hint is not None:
        sl = float(sl_hint)
        if side == "LONG":
            sl = min(sl, entry)
        else:
            sl = max(sl, entry)
        return tps, sl, "fractal"

    sl  = entry * (1 - mult*sl_pct)
    return tps, sl, "percent"

def analyze() -> list[dict]:
    s = get_settings()
    router = ExchangeRouter.from_env()

    signals = []
    used_exchange = None

    for symbol in s.symbols:
        ex_id, df = router.fetch_ohlcv_df(symbol, timeframe=s.timeframe, limit=200)
        used_exchange = ex_id  # último exitoso (para nota)
        df = add_ema(add_ema(df, s.ema_fast), s.ema_slow)
        sig = ema_fractal_signal(
            df,
            s.ema_fast,
            s.ema_slow,
            lookback=s.fractal_lookback,
            require_fractal=s.use_fractal_filter,
        )
        if not sig:
            continue

        tps, sl, sl_source = _build_tps_sl(
            sig["entry"],
            sig["side"],
            s.tp_pcts,
            s.sl_pct,
            sl_hint=sig.get("sl_hint"),
        )

        signals.append({
            "symbol": symbol,
            "tf": s.timeframe,
            "side": sig["side"],
            "entry_lo": sig["entry"],
            "entry_hi": sig["entry"],
            "sl": sl,
            "tps": tps,
            "sl_source": sl_source,
            "fractals": sig.get("fractals"),
            "risk_pct": sig.get("risk_pct"),
        })

    if not signals:
        # sin señales -> devolvemos lista vacía (el ciclo mandará BOT iniciado + finalizado 0 alertas)
        return []

    note = f"Fuente: {used_exchange} (failover activo)" if used_exchange else None
    html = fmt.signals_digest_html(signals, note=note, ts=datetime.now(timezone.utc))
    return [{
        "text": html,
        "parse_mode": "HTML",
        "signals_count": len(signals),
    }]
