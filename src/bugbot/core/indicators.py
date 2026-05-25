from __future__ import annotations
import numpy as np
import pandas as pd


def add_ema(
    df: pd.DataFrame,
    period: int,
    col: str = "close",
    name: str | None = None,
) -> pd.DataFrame:
    name = name or f"ema{period}"
    df[name] = df[col].ewm(span=period, adjust=False).mean()
    return df

def detect_fractals(
    df: pd.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    left: int = 2,
    right: int = 2,
    prefix: str = "fractal",
) -> pd.DataFrame:
    """Marca fractales de Bill Williams sobre un DataFrame OHLCV.

    Un fractal "bearish" se forma cuando el máximo de la vela central es
    estrictamente mayor que los *left* máximos anteriores y los *right* máximos
    siguientes. El fractal "bullish" es análogo con los mínimos.

    Parameters
    ----------
    df:
        DataFrame con columnas OHLCV.
    high_col / low_col:
        Columnas a utilizar para máximos y mínimos.
    left / right:
        Número de velas a cada lado que deben confirmar el fractal.
    prefix:
        Prefijo para las columnas resultantes (por defecto ``fractal``).

    Returns
    -------
    DataFrame con columnas booleanas ``{prefix}_bearish`` y ``{prefix}_bullish``.
    """
    if df.empty:
        out = df.copy()
        out[f"{prefix}_bearish"] = False
        out[f"{prefix}_bullish"] = False
        return out

    out = df.copy()
    highs = out[high_col]
    lows = out[low_col]

    bear = pd.Series(True, index=out.index, dtype="bool")
    bull = pd.Series(True, index=out.index, dtype="bool")

    for i in range(1, max(left, 0) + 1):
        bear &= highs > highs.shift(i)
        bull &= lows < lows.shift(i)

    for j in range(1, max(right, 0) + 1):
        bear &= highs > highs.shift(-j)
        bull &= lows < lows.shift(-j)

    out[f"{prefix}_bearish"] = bear.fillna(False)
    out[f"{prefix}_bullish"] = bull.fillna(False)
    return out

import numpy as np
import pandas as pd
# ==== ADVANCED INDICATORS (helpers + bundles) ================================

def _ensure_atr(df: pd.DataFrame, n: int = 14):
    if "atr14" in df.columns:
        return df
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"]  - df["close"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(n).mean()
    return df

def add_dmi_adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm  = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift()).abs()
    tr3 = (df["low"]  - df["close"].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()

    plus_di  = 100 * (pd.Series(plus_dm, index=df.index).rolling(n).sum() / atr)
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).rolling(n).sum() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(n).mean()

    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx"] = adx
    return df

def add_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    df["macd"] = macd
    df["macd_signal"] = macd_signal
    df["macd_hist"] = macd - macd_signal
    return df

def add_vwap_daily(df: pd.DataFrame) -> pd.DataFrame:
    # Reinicia por día; requiere columna 'volume'
    day = getattr(df.index, "date", df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    cum_pv = (tp * df["volume"]).groupby(day).cumsum()
    cum_v  = df["volume"].groupby(day).cumsum()
    df["vwap"] = cum_pv / cum_v
    return df

def add_bbands_keltner(df: pd.DataFrame, n=20, k_bb=2.0, k_kc=1.5) -> pd.DataFrame:
    ma = df["close"].rolling(n).mean()
    std = df["close"].rolling(n).std(ddof=0)
    df["bb_up"] = ma + k_bb * std
    df["bb_dn"] = ma - k_bb * std

    ema = df["close"].ewm(span=n, adjust=False).mean()
    tr = (pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs()
    ], axis=1).max(axis=1)).rolling(n).mean()
    df["kc_up"] = ema + k_kc * tr
    df["kc_dn"] = ema - k_kc * tr

    df["squeeze_on"] = (df["bb_up"] <= df["kc_up"]) & (df["bb_dn"] >= df["kc_dn"])
    return df

def add_donchian(df: pd.DataFrame, n=20) -> pd.DataFrame:
    df["don_high"] = df["high"].rolling(n).max()
    df["don_low"]  = df["low"].rolling(n).min()
    return df

def add_supertrend(df: pd.DataFrame, n=10, m=3) -> pd.DataFrame:
    hl2 = (df["high"] + df["low"]) / 2
    tr = (pd.concat([
        (df["high"]-df["low"]),
        (df["high"]-df["close"].shift()).abs(),
        (df["low"] -df["close"].shift()).abs()
    ], axis=1).max(axis=1))
    atr = tr.rolling(n).mean()
    upper = hl2 + m * atr
    lower = hl2 - m * atr

    st = pd.Series(index=df.index, dtype=float)
    for i in range(len(df)):
        if i == 0:
            st.iat[i] = upper.iat[i]
            continue
        prev = st.iat[i-1]
        st.iat[i] = upper.iat[i] if df["close"].iat[i-1] <= prev else lower.iat[i]
        if df["close"].iat[i] > st.iat[i] and st.iat[i] < prev: st.iat[i] = prev
        if df["close"].iat[i] < st.iat[i] and st.iat[i] > prev: st.iat[i] = prev
    df["supertrend"] = st
    df["st_dir"] = (df["close"] > df["supertrend"]).astype(int)
    return df

def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    obv = [0]
    for i in range(1, len(df)):
        if df["close"].iat[i] > df["close"].iat[i-1]:
            obv.append(obv[-1] + df["volume"].iat[i])
        elif df["close"].iat[i] < df["close"].iat[i-1]:
            obv.append(obv[-1] - df["volume"].iat[i])
        else:
            obv.append(obv[-1])
    df["obv"] = pd.Series(obv, index=df.index)
    return df

def add_indicators_15m(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_atr(df, 14)
    df = add_dmi_adx(df, 14)
    df = add_macd(df)
    df = add_vwap_daily(df)
    df = add_bbands_keltner(df)
    df = add_donchian(df, 20)
    df = add_supertrend(df)
    df = add_obv(df)
    return df

def add_indicators_4h(df: pd.DataFrame) -> pd.DataFrame:
    df = _ensure_atr(df, 14)
    df = add_dmi_adx(df, 14)
    return df


