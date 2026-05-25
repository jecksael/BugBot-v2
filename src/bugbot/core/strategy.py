from __future__ import annotations

import pandas as pd

from .indicators import detect_fractals


def ema_cross_signal(df: pd.DataFrame, fast: int, slow: int) -> dict | None:
    """
    Señal si en la ÚLTIMA vela hay cruce:
      - LONG  si ema_fast cruza por arriba de ema_slow
      - SHORT si ema_fast cruza por abajo
    Devuelve dict con side, entry, sl, tps o None si no hay cruce.
    """
    ef, es = f"ema{fast}", f"ema{slow}"
    if len(df) < 2 or ef not in df or es not in df:
        return None

    f_prev, s_prev = float(df[ef].iloc[-2]), float(df[es].iloc[-2])
    f_now,  s_now  = float(df[ef].iloc[-1]),  float(df[es].iloc[-1])
    close = float(df["close"].iloc[-1])

    crossed_up   = f_prev <= s_prev and f_now > s_now
    crossed_down = f_prev >= s_prev and f_now < s_now

    if not (crossed_up or crossed_down):
        return None

    side = "LONG" if crossed_up else "SHORT"
    return {"side": side, "entry": close}


def _extract_last_fractal(
    df: pd.DataFrame,
    column: str,
) -> tuple[int, float] | None:
    rows = df[df[column]]
    if rows.empty:
        return None

    last_idx = rows.index[-1]
    loc = df.index.get_loc(last_idx)
    if isinstance(loc, slice):
        pos = loc.stop - 1
    elif isinstance(loc, (list, tuple)):
        pos = loc[-1]
    elif hasattr(loc, "__iter__") and not isinstance(loc, (int, slice)):
        loc_list = list(loc)
        pos = loc_list[-1]
    else:
        pos = int(loc)

    price = float(df.iloc[pos]["low" if "bull" in column else "high"])
    return pos, price


def ema_fractal_signal(
    df: pd.DataFrame,
    fast: int,
    slow: int,
    *,
    lookback: int = 5,
    require_fractal: bool = True,
) -> dict | None:
    """Combina el cruce de EMAs con la alineación de fractales cercanos."""

    cross = ema_cross_signal(df, fast, slow)
    if not cross:
        return None

    enriched = detect_fractals(df.copy())
    side = cross["side"].upper()
    col = "fractal_bullish" if side == "LONG" else "fractal_bearish"

    out = _extract_last_fractal(enriched, col)
    if out is None:
        if require_fractal:
            return None
        fractal_meta = None
    else:
        pos, price = out
        bars_ago = len(enriched) - 1 - pos
        if require_fractal and bars_ago > lookback:
            return None
        fractal_meta = {
            "type": "bullish" if side == "LONG" else "bearish",
            "price": price,
            "bars_ago": bars_ago,
        }

    entry = cross["entry"]
    if fractal_meta:
        risk = abs(entry - fractal_meta["price"]) / max(entry, 1e-9)
    else:
        risk = None

    return {
        "side": side,
        "entry": entry,
        "fractals": fractal_meta,
        "risk_pct": risk,
        "sl_hint": fractal_meta["price"] if fractal_meta else None,
    }
