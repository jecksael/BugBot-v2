# src/bugbot/adapters/data.py
"""
BugBot v2.0 — Data Adapter
Fuente: yfinance (desarrollo) → Tradovate (live)
"""
from __future__ import annotations
import pandas as pd
import yfinance as yf

# Mapeo de símbolos BugBot → yfinance
SYMBOL_MAP = {
    "NQ":  "NQ=F",
    "MNQ": "MNQ=F",
    "MES": "MES=F",
    "MGC": "MGC=F",
}

# Mapeo de timeframes
TIMEFRAME_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
}

def fetch_ohlcv(
    symbol:    str,
    timeframe: str = "5m",
    bars:      int = 200,
) -> pd.DataFrame:
    """
    Descarga datos OHLCV de yfinance y los normaliza
    para que el engine los pueda procesar.
    """
    sym = symbol.upper()
    yf_sym = SYMBOL_MAP.get(sym)
    if not yf_sym:
        raise ValueError(f"Símbolo no soportado: {sym}. Usa NQ, MES o MGC.")

    tf = TIMEFRAME_MAP.get(timeframe, "5m")

    # Período según timeframe
    period_map = {
        "1m": "1d", "5m": "5d", "15m": "5d",
        "1h": "1mo", "4h": "1mo", "1d": "6mo",
    }
    period = period_map.get(tf, "5d")

    raw = yf.download(yf_sym, period=period, interval=tf, progress=False)

    if raw.empty:
        raise RuntimeError(f"No se obtuvieron datos para {sym}")

    # Aplanar columnas multi-nivel
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = [col[0].lower() for col in raw.columns]
    else:
        raw.columns = [col.lower() for col in raw.columns]

    # Seleccionar solo columnas necesarias
    df = raw[["open", "high", "low", "close", "volume"]].copy()
    df.index.name = "datetime"
    df = df.dropna()
    df = df.tail(bars)

    return df