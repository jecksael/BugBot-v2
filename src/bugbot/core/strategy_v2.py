# src/bugbot/core/strategy_v2.py
"""
BugBot v2.0 — Strategy Engine para MNQ/MES/MGC
Basado en: EMA 21/50 + VWAP + Soporte/Resistencia + Volumen
"""
from __future__ import annotations
import pandas as pd
import numpy as np

# ─── Indicadores ──────────────────────────────────────────────────────────────

def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    return df

def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (tp * df["volume"]).cumsum() / df["volume"].cumsum()
    return df

def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df["vol_sma"] = df["volume"].rolling(period).mean()
    return df

def add_swing_levels(df: pd.DataFrame, lookback: int = 10) -> pd.DataFrame:
    """Detecta swings highs y lows para S/R"""
    df["swing_high"] = df["high"][(
        df["high"] == df["high"].rolling(lookback, center=True).max()
    )]
    df["swing_low"] = df["low"][(
        df["low"] == df["low"].rolling(lookback, center=True).min()
    )]
    return df

# ─── Bias del día ─────────────────────────────────────────────────────────────

def get_bias(df: pd.DataFrame) -> str:
    """
    Bias basado en EMA 21 vs EMA 50
    LONG  → ema21 > ema50 y precio sobre ambas
    SHORT → ema21 < ema50 y precio bajo ambas
    NEUTRAL → sin tendencia clara
    """
    last = df.iloc[-1]
    ema21 = last["ema21"]
    ema50 = last["ema50"]
    close = last["close"]
    vwap  = last["vwap"]

    if ema21 > ema50 and close > ema21 and close > vwap:
        return "LONG"
    if ema21 < ema50 and close < ema21 and close < vwap:
        return "SHORT"
    return "NEUTRAL"

# ─── Detector de señales ──────────────────────────────────────────────────────

def detect_signal(df: pd.DataFrame) -> dict | None:
    """
    Detecta señal cuando:
    LONG:
      - EMA 21 > EMA 50 (tendencia alcista)
      - Precio toca o rebota en EMA 21 o VWAP
      - Volumen actual > SMA volumen (confirmación)
      - Vela de rechazo alcista (close > open)

    SHORT:
      - EMA 21 < EMA 50 (tendencia bajista)
      - Precio toca o rebota en EMA 21 o VWAP
      - Volumen actual > SMA volumen
      - Vela de rechazo bajista (close < open)
    """
    if len(df) < 50:
        return None

    df = add_emas(df)
    df = add_vwap(df)
    df = add_volume_sma(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    bias  = get_bias(df)
    if bias == "NEUTRAL":
        return None

    close  = last["close"]
    open_  = last["open"]
    ema21  = last["ema21"]
    vwap   = last["vwap"]
    vol    = last["volume"]
    vol_sm = last["vol_sma"]

    # Tolerancia para tocar EMA/VWAP (0.1%)
    tol = close * 0.001

    toca_ema21 = abs(last["low"] - ema21) <= tol or abs(last["high"] - ema21) <= tol
    toca_vwap  = abs(last["low"] - vwap)  <= tol or abs(last["high"] - vwap)  <= tol
    vol_ok     = vol > vol_sm
    en_zona    = toca_ema21 or toca_vwap

    if not en_zona or not vol_ok:
        return None

    # LONG
    if bias == "LONG" and close > open_:
        sl = last["low"] - (close * 0.0005)
        return {
            "side":    "LONG",
            "entry":   close,
            "sl":      round(sl, 2),
            "bias":    bias,
            "zona":    "EMA21" if toca_ema21 else "VWAP",
            "vol_ok":  vol_ok,
        }

    # SHORT
    if bias == "SHORT" and close < open_:
        sl = last["high"] + (close * 0.0005)
        return {
            "side":    "SHORT",
            "entry":   close,
            "sl":      round(sl, 2),
            "bias":    bias,
            "zona":    "EMA21" if toca_ema21 else "VWAP",
            "vol_ok":  vol_ok,
        }

    return None