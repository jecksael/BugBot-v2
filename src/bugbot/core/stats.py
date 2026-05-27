# src/bugbot/core/stats.py
"""
BugBot v2.0 — Módulo de estadísticas de moves
Analiza swings históricos para calibrar TPs y entender el mercado
"""
from __future__ import annotations
import pandas as pd
import numpy as np

def calc_daily_stats(df: pd.DataFrame) -> dict:
    """
    Calcula estadísticas del movimiento diario:
    - Move promedio diario (High - Low)
    - Move promedio de apertura (primeros 30 min)
    - % días alcistas vs bajistas
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)

    # Agrupar por día
    daily = df.groupby(df.index.date).agg(
        high  = ("high",  "max"),
        low   = ("low",   "min"),
        open  = ("open",  "first"),
        close = ("close", "last"),
    )

    daily["range"]    = daily["high"] - daily["low"]
    daily["bullish"]  = daily["close"] > daily["open"]

    return {
        "avg_daily_range":   round(daily["range"].mean(), 2),
        "max_daily_range":   round(daily["range"].max(), 2),
        "min_daily_range":   round(daily["range"].min(), 2),
        "pct_bullish_days":  round(daily["bullish"].mean() * 100, 1),
        "pct_bearish_days":  round((~daily["bullish"]).mean() * 100, 1),
        "days_analyzed":     len(daily),
    }

def calc_swing_stats(df: pd.DataFrame, lookback: int = 10) -> dict:
    """
    Detecta swings y calcula:
    - Move promedio de swing up
    - Move promedio de swing down
    - Duración promedio de swing
    """
    highs = []
    lows  = []

    for i in range(lookback, len(df) - lookback):
        window_high = df["high"].iloc[i-lookback:i+lookback]
        window_low  = df["low"].iloc[i-lookback:i+lookback]

        if df["high"].iloc[i] == window_high.max():
            highs.append(float(df["high"].iloc[i]))
        if df["low"].iloc[i] == window_low.min():
            lows.append(float(df["low"].iloc[i]))

    if len(highs) < 2 or len(lows) < 2:
        return {"error": "Datos insuficientes para calcular swings"}

    swing_ups   = [abs(highs[i] - lows[i])   for i in range(min(len(highs), len(lows)))]
    swing_downs = [abs(highs[i] - lows[i+1]) for i in range(min(len(highs), len(lows)-1))]

    return {
        "avg_swing_up":   round(np.mean(swing_ups), 2),
        "avg_swing_down": round(np.mean(swing_downs), 2),
        "max_swing":      round(max(swing_ups + swing_downs), 2),
        "min_swing":      round(min(swing_ups + swing_downs), 2),
        "swings_detected": len(swing_ups),
    }

def calc_vwap_stats(df: pd.DataFrame) -> dict:
    """
    Estadísticas de respeto al VWAP:
    - % velas que rebotan en VWAP
    - Move promedio después de tocar VWAP
    """
    df = df.copy()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (tp * df["volume"]).cumsum() / df["volume"].cumsum()

    tol = df["close"] * 0.001
    toca_vwap = (
        (df["low"] - df["vwap"]).abs() <= tol
    ) | (
        (df["high"] - df["vwap"]).abs() <= tol
    )

    rebounds = 0
    for i in range(len(df) - 1):
        if toca_vwap.iloc[i]:
            next_move = abs(df["close"].iloc[i+1] - df["close"].iloc[i])
            if next_move > 0:
                rebounds += 1

    total_touches = toca_vwap.sum()

    return {
        "vwap_touches":      int(total_touches),
        "vwap_rebounds":     rebounds,
        "vwap_respect_pct":  round((rebounds / max(total_touches, 1)) * 100, 1),
    }

def full_report(symbol: str, df: pd.DataFrame) -> str:
    """
    Genera reporte completo de estadísticas para Telegram
    """
    daily  = calc_daily_stats(df)
    swings = calc_swing_stats(df)
    vwap   = calc_vwap_stats(df)

    return (
        f"📊 <b>Estadísticas {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>📅 Movimiento diario ({daily['days_analyzed']} días):</b>\n"
        f"• Rango promedio: <code>{daily['avg_daily_range']}</code> pts\n"
        f"• Rango máximo:   <code>{daily['max_daily_range']}</code> pts\n"
        f"• Rango mínimo:   <code>{daily['min_daily_range']}</code> pts\n"
        f"• Días alcistas:  <code>{daily['pct_bullish_days']}%</code>\n"
        f"• Días bajistas:  <code>{daily['pct_bearish_days']}%</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>📈 Swings detectados:</b>\n"
        f"• Swing up prom:   <code>{swings.get('avg_swing_up', 'N/A')}</code> pts\n"
        f"• Swing down prom: <code>{swings.get('avg_swing_down', 'N/A')}</code> pts\n"
        f"• Swing máximo:    <code>{swings.get('max_swing', 'N/A')}</code> pts\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>💧 VWAP:</b>\n"
        f"• Toques:   <code>{vwap['vwap_touches']}</code>\n"
        f"• Rebotes:  <code>{vwap['vwap_rebounds']}</code>\n"
        f"• Respeto:  <code>{vwap['vwap_respect_pct']}%</code>\n"
    )