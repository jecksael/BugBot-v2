# src/bugbot/strategies/advanced.py
from __future__ import annotations
from typing import List
from ..core.types import Signal
from ..core.risk import make_targets

# ---------- Helpers comunes ----------
def _ignition(row) -> bool:
    rng = (row["high"] - row["low"])
    if rng <= 0:
        return False
    body = abs(row["close"] - row["open"])
    return (body / rng) >= 0.60

def _macro_flags_4h(r4h) -> dict:
    bull = (r4h["ema21"] > r4h["ema52"] > r4h["ema100"]
            and r4h["close"] > r4h["ema21"]
            and r4h.get("adx", 20) >= 18)
    bear = (r4h["ema21"] < r4h["ema52"] < r4h["ema100"]
            and r4h["close"] < r4h["ema21"]
            and r4h.get("adx", 20) >= 18)
    return {"macro_long": bull, "macro_short": bear}

# ---------- SNIPER 15m ----------
def _score_sniper(r15, macro: dict, side: str) -> float:
    score = 0.0
    score += 0.30 if (macro["macro_long"] if side == "long" else macro["macro_short"]) else 0.0
    score += 0.20 if r15.get("adx", 0) >= 20 else 0.0
    hist = r15.get("macd_hist", 0.0)
    score += 0.20 if (hist > 0 if side == "long" else hist < 0) else 0.0
    vwap_ok = r15["close"] > r15.get("vwap", 0) if side == "long" else r15["close"] < r15.get("vwap", 9e9)
    score += 0.10 if vwap_ok else 0.0
    score += 0.20 if _ignition(r15) else 0.0
    return round(min(score, 1.0), 2)

def find_signals_sniper_15m(ex_id: str, symbol: str, df15, df4h) -> List[Signal]:
    r15 = df15.iloc[-1]
    r4h = df4h.iloc[-1]
    macro = _macro_flags_4h(r4h)
    sigs: List[Signal] = []

    # LONG
    if (macro["macro_long"]
        and r15["ema21"] > r15["ema52"] > r15["ema100"]
        and r15["low"] <= r15["ema21"] < r15["close"]
        and r15.get("rsi14", 50) >= 50
        and r15.get("adx", 0) >= 20
        and r15.get("macd_hist", 0) > 0
        and r15["close"] > r15.get("vwap", 0)
        and _ignition(r15)):
        entry = float(r15["close"])
        atr   = float(r15.get("atr14", 0.0))
        sl, tps, R = make_targets("long", entry, atr)
        reasons = ["macro_4H_bull", "pullback_ema21", "rsi>=50", "adx>=20", "macd_hist>0", "close>vwap", "ignition"]
        sigs.append(Signal(
            ts_utc=str(r15.name), exchange=ex_id, symbol=symbol, timeframe="15m",
            rule="SNIPER_15M", side="long", reasons=reasons, entry=entry, sl=sl, tp=tps, R=R,
            score=_score_sniper(r15, macro, "long")
        ))

    # SHORT
    if (macro["macro_short"]
        and r15["ema21"] < r15["ema52"] < r15["ema100"]
        and r15["high"] >= r15["ema21"] > r15["close"]
        and r15.get("rsi14", 50) <= 50
        and r15.get("adx", 0) >= 20
        and r15.get("macd_hist", 0) < 0
        and r15["close"] < r15.get("vwap", 9e9)
        and _ignition(r15)):
        entry = float(r15["close"])
        atr   = float(r15.get("atr14", 0.0))
        sl, tps, R = make_targets("short", entry, atr)
        reasons = ["macro_4H_bear", "pullback_ema21", "rsi<=50", "adx>=20", "macd_hist<0", "close<vwap", "ignition"]
        sigs.append(Signal(
            ts_utc=str(r15.name), exchange=ex_id, symbol=symbol, timeframe="15m",
            rule="SNIPER_15M", side="short", reasons=reasons, entry=entry, sl=sl, tp=tps, R=R,
            score=_score_sniper(r15, macro, "short")
        ))
    return sigs

# ---------- GATO 15m ----------
def _range_levels(df15, lookback=50):
    win = df15.tail(lookback)
    rng_hi = float(win["high"].max())
    rng_lo = float(win["low"].min())
    mid    = (rng_hi + rng_lo) / 2.0
    last   = win.iloc[-1]
    ema_diff_ratio = abs(last["ema21"] - last["ema52"]) / max(1e-9, last["close"])
    width_ratio    = (rng_hi - rng_lo) / max(1e-9, last["close"])
    squeeze_on     = bool(last.get("squeeze_on", False))
    return rng_hi, rng_lo, mid, ema_diff_ratio, width_ratio, squeeze_on

def _recent_fake_break(df15, level: float, kind: str, max_bars_reentry=3) -> tuple[bool, int]:
    found, bars_ago = False, 0
    for i in range(1, max_bars_reentry + 1):
        row = df15.iloc[-1 - i]
        if kind == "down" and row["low"] < level:
            found, bars_ago = True, i; break
        if kind == "up" and row["high"] > level:
            found, bars_ago = True, i; break
    if not found:
        return False, 0
    last = df15.iloc[-1]
    if kind == "down" and last["close"] > level: return True, bars_ago
    if kind == "up"   and last["close"] < level: return True, bars_ago
    return False, bars_ago

def _score_gato(r15, side, squeeze_on, width_ratio, bars_ago_break):
    score = 0.0
    score += 0.35 if r15.get("adx", 99) < 18 else 0.0
    score += 0.15 if (squeeze_on or width_ratio < 0.02) else 0.0
    score += 0.25 if (1 <= bars_ago_break <= 3) else 0.0
    score += 0.15 if ((r15.get("rsi14", 50) >= 45) if side == "long" else (r15.get("rsi14", 50) <= 55)) else 0.0
    score += 0.10 if _ignition(r15) else 0.0
    return round(min(score, 1.0), 2)

def find_signals_gato_15m(
    ex_id: str,
    symbol: str,
    df15,
    df4h,
    *,
    lookback: int = 50,
    adx_max: float = 18,
    max_bars_reentry: int = 3
) -> List[Signal]:
    sigs: List[Signal] = []
    r15 = df15.iloc[-1]

    # Evita Gato si 4H está tendencial fuerte
    macro = _macro_flags_4h(df4h.iloc[-1])
    if macro["macro_long"] or macro["macro_short"]:
        return sigs

    rng_hi, rng_lo, mid, ema_diff_ratio, width_ratio, squeeze_on = _range_levels(df15, lookback)

    # Mercado en rango / baja tendencia
    if not (r15.get("adx", 99) < adx_max and (squeeze_on or ema_diff_ratio < 0.002 or width_ratio < 0.02)):
        return sigs

    # LONG: fake breakdown + reingreso
    fb_long, bars_ago = _recent_fake_break(df15, rng_lo, kind="down", max_bars_reentry=max_bars_reentry)
    if fb_long and r15.get("rsi14", 50) >= 45:
        entry = float(r15["close"]); atr = float(r15.get("atr14", 0.0))
        low_break = float(df15.tail(max_bars_reentry + 1)["low"].min())
        sl = min(low_break, entry - 1.0 * atr)
        R = entry - sl
        tps = [mid, entry + 1 * R, entry + 2 * R]
        reasons = ["range_mode(adx<18)", "fake-breakdown_reentry",
                   "squeeze_or_narrow" if squeeze_on or width_ratio < 0.02 else "ema21≈ema52", "rsi>=45"]
        sigs.append(Signal(
            ts_utc=str(r15.name), exchange=ex_id, symbol=symbol, timeframe="15m",
            rule="GATO_15M", side="long", reasons=reasons, entry=entry, sl=sl, tp=tps, R=R,
            score=_score_gato(r15, "long", squeeze_on, width_ratio, bars_ago),
        ))

    # SHORT: fake breakout + reingreso
    fb_short, bars_ago = _recent_fake_break(df15, rng_hi, kind="up", max_bars_reentry=max_bars_reentry)
    if fb_short and r15.get("rsi14", 50) <= 55:
        entry = float(r15["close"]); atr = float(r15.get("atr14", 0.0))
        high_break = float(df15.tail(max_bars_reentry + 1)["high"].max())
        sl = max(high_break, entry + 1.0 * atr)
        R = sl - entry
        tps = [mid, entry - 1 * R, entry - 2 * R]
        reasons = ["range_mode(adx<18)", "fake-breakout_reentry",
                   "squeeze_or_narrow" if squeeze_on or width_ratio < 0.02 else "ema21≈ema52", "rsi<=55"]
        sigs.append(Signal(
            ts_utc=str(r15.name), exchange=ex_id, symbol=symbol, timeframe="15m",
            rule="GATO_15M", side="short", reasons=reasons, entry=entry, sl=sl, tp=tps, R=R,
            score=_score_gato(r15, "short", squeeze_on, width_ratio, bars_ago),
        ))

    return sigs
