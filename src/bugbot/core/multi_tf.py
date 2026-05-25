from __future__ import annotations
import pandas as pd

def _ensure_ema(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    fcol, scol = f"ema{fast}", f"ema{slow}"
    if fcol not in out.columns:
        out[fcol] = out["close"].ewm(span=fast, adjust=False).mean()
    if scol not in out.columns:
        out[scol] = out["close"].ewm(span=slow, adjust=False).mean()
    return out

def weekly_bias(dfw: pd.DataFrame, band=0.05, tilt_ok=0.995, fast=21, slow=52) -> str:
    """
    Bull/Bear/Neutral macro con EMAs en 1W.
    - bear: ema_fast < ema_slow * tilt_ok
    - neutral: |ema_fast - ema_slow|/close <= band
    - bull: else
    """
    dfw = _ensure_ema(dfw, fast, slow)
    close = float(dfw["close"].iloc[-1])
    efast = float(dfw[f"ema{fast}"].iloc[-1])
    eslow = float(dfw[f"ema{slow}"].iloc[-1])

    if efast < eslow * tilt_ok:
        return "bear"
    diff = abs(efast - eslow) / max(close, 1e-9)
    if diff <= band:
        return "neutral"
    return "bull"

def trend_4h(df4: pd.DataFrame, fast=21, slow=52) -> str:
    """
    up / down / chop en 4H.
    - chop: EMAs muy juntas respecto al precio
    - up: ema_fast > ema_slow
    - down: caso contrario
    """
    df4 = _ensure_ema(df4, fast, slow)
    close = float(df4["close"].iloc[-1])
    efast = float(df4[f"ema{fast}"].iloc[-1])
    eslow = float(df4[f"ema{slow}"].iloc[-1])

    tight = abs(efast - eslow) / max(close, 1e-9)
    if tight < 0.0025:
        return "chop"
    return "up" if efast > eslow else "down"

def ema_cross_1h(df1: pd.DataFrame, fast=21, slow=52):
    """
    Detecta cruce en la ÚLTIMA vela 1H.
    - LONG si antes fast<=slow y ahora fast>slow
    - SHORT si antes fast>=slow y ahora fast<slow
    - None si no hay evento
    """
    if len(df1) < max(fast, slow) + 2:
        return None
    df1 = _ensure_ema(df1, fast, slow)
    fcol, scol = f"ema{fast}", f"ema{slow}"

    prev_fast = float(df1[fcol].iloc[-2])
    prev_slow = float(df1[scol].iloc[-2])
    cur_fast = float(df1[fcol].iloc[-1])
    cur_slow = float(df1[scol].iloc[-1])

    if prev_fast <= prev_slow and cur_fast > cur_slow:
        return "LONG"
    if prev_fast >= prev_slow and cur_fast < cur_slow:
        return "SHORT"
    return None

def confirm_15m_align(df15: pd.DataFrame, fast=21, slow=52, bars=3, side: str | None = None):
    """
    Confirma que en las últimas N velas de 15m las EMAs estén alineadas
    con el 'side' previsto (LONG/SHORT).
    """
    if side not in ("LONG", "SHORT"):
        return None
    if len(df15) < max(fast, slow) + bars:
        return None

    df15 = _ensure_ema(df15, fast, slow)
    fcol, scol = f"ema{fast}", f"ema{slow}"
    last = df15.tail(bars)

    if side == "LONG" and (last[fcol] > last[scol]).all():
        return "LONG"
    if side == "SHORT" and (last[fcol] < last[scol]).all():
        return "SHORT"
    return None
