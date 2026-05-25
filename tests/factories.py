# tests/factories.py
from __future__ import annotations
import pandas as pd

def _normalize_freq(freq: str) -> str:
    if not isinstance(freq, str):
        return freq
    # horas en minúscula (pandas prefiere 'h')
    if freq[-1] in ("H", "h"):
        return freq[:-1] + "h"
    # semanas en MAYÚSCULA (pandas prefiere 'W')
    if freq[-1] in ("W", "w"):
        return freq[:-1] + "W"
    # días: pandas suele preferir 'D' mayúscula
    if freq[-1] in ("D", "d"):
        return freq[:-1] + "D"
    return freq

def make_df_from_closes(closes, freq="1H"):
    idx = pd.date_range(
        "2024-01-01",
        periods=len(closes),
        freq=_normalize_freq(freq),
        tz="UTC",
    )
    s = pd.Series(closes, index=idx, dtype="float64")
    df = pd.DataFrame({
        "date": idx,
        "open": s.shift(1).fillna(s.iloc[0]),
        "high": s * 1.01,
        "low":  s * 0.99,
        "close": s,
        "volume": 1.0,
    })
    return df

def add_emas(df, fast=21, slow=52):
    out = df.copy()
    out[f"ema{fast}"] = out["close"].ewm(span=fast, adjust=False).mean()
    out[f"ema{slow}"] = out["close"].ewm(span=slow, adjust=False).mean()
    return out
