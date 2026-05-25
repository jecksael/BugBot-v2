from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import os
import time
import pandas as pd
import ccxt  # type: ignore
from ..config.settings import get_settings

TIMEFRAME_MAP = {
    "1H": "1h",
    "4H": "4h",
    "1D": "1d",
    "1W": "1w",
    "STR": "15m",   # ← si tu “STR” significa 15m; cambia aquí si debe ser otro
}
def _resolve_timeframe(raw, tf_raw) -> str:
    """
    Normaliza el timeframe que llega desde settings o CLI.
    Se asegura de que esté soportado por el exchange.
    """
    tf = str(tf_raw).upper() if tf_raw is not None else "STR"
    tf_eff = TIMEFRAME_MAP.get(tf, tf.lower())

    supported = getattr(raw, "timeframes", {}) or {}
    if tf_eff in supported:
        return tf_eff

    # fallback a un timeframe común
    for cand in ("15m", "1h", "4h", "1d"):
        if cand in supported:
            return cand

    raise ValueError(f"Timeframe no soportado en {raw.id}: {tf} -> {tf_eff}")
def _resolve_symbol(raw, symbol: str) -> str:
    symbol = symbol.upper()
    raw.load_markets()

    # Si ya existe tal cual
    if symbol in raw.symbols:
        return symbol

    cands = [symbol]

    # Caso Kraken BTC -> XBT
    if raw.id == "kraken":
        if symbol.startswith("BTC/"):
            cands.append(symbol.replace("BTC/", "XBT/"))
        elif symbol.startswith("XBT/"):
            cands.append(symbol.replace("XBT/", "BTC/"))

    # Verifica candidatos en los markets cargados
    for c in cands:
        if c in raw.symbols:
            return c

    raise ValueError(f"Símbolo no soportado en {raw.id}: {symbol} (candidatos: {cands})")

def _build_exchange(exchange_id: str, api_key: str | None, api_secret: str | None, api_passphrase: str | None):
    klass = getattr(ccxt, exchange_id)
    return klass({
        "enableRateLimit": True,
        "apiKey": api_key,
        "secret": api_secret,
        "password": api_passphrase,
    })

@dataclass
class ExchangeRouter:
    def __init__(self, raw):
        self.raw = raw
        self.settings = get_settings()

    @classmethod
    def from_env(cls):
        s = get_settings()
        exchanges = getattr(s, "exchanges", []) or []

        selected_exchange: str | None = None
        for candidate in exchanges:
            if not candidate:
                continue
            candidate_str = str(candidate).strip()
            if candidate_str:
                selected_exchange = candidate_str
                break

        if not selected_exchange:
            selected_exchange = "kraken"

        ex_id = selected_exchange.lower()

        if not hasattr(ccxt, ex_id):
            raise ValueError(f"Exchange no soportado en ccxt: {selected_exchange}")

        ExchangeClass = getattr(ccxt, ex_id)
        params = {"enableRateLimit": True}

        # si tienes claves en settings, úsalas (nombres típicos; ajusta a los tuyos si cambian)
        for k_src, k_dst in [("API_KEY","apiKey"), ("api_key","apiKey"), ("API_SECRET","secret"), ("api_secret","secret")]:
            v = getattr(s, k_src, None)
            if v:
                params[k_dst] = v

        raw = ExchangeClass(params)
        return cls(raw)

    def fetch_candles(self, symbol: str):
        sym = _resolve_symbol(self.raw, symbol)  # BTC->XBT si es Kraken
        tf_raw = getattr(self.settings, "TF", None) or getattr(self.settings, "timeframe", None) or "STR"
        tf_eff = _resolve_timeframe(self.raw, tf_raw)  # STR->15m (o lo que definiste)
        return self.raw.fetch_ohlcv(sym, timeframe=tf_eff, limit=200)
    
    def fetch_ohlcv_df(self, symbol: str, timeframe=None, limit: int = 200, since=None, **_):
        """
        Devuelve OHLCV en DataFrame.
        Soporta kwargs como timeframe/limit/since que puede pasar la CLI.
        """
        # 1) símbolo efectivo (BTC→XBT en Kraken)
        sym = _resolve_symbol(self.raw, symbol)

        # 2) timeframe efectivo (si no viene, lee settings y mapea STR, 1H, etc.)
        tf_raw = (
            timeframe
            or getattr(self.settings, "TF", None)
            or getattr(self.settings, "timeframe", None)
            or "STR"
        )
        tf_eff = _resolve_timeframe(self.raw, tf_raw)

        # 3) normaliza 'since' si viene (ccxt espera epoch en ms)
        if isinstance(since, float) or isinstance(since, int):
            since_ms = int(since)
            # si parece estar en segundos, pásalo a ms
            if since_ms < 10_000_000_000:  # ~< year 2286
                since_ms *= 1000
        else:
            since_ms = None

        # 4) fetch seguro
        ohlcv = self.raw.fetch_ohlcv(sym, timeframe=tf_eff, limit=limit, since=since_ms)

        # 5) a DataFrame
        import pandas as pd
        df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        return self.raw.id, df
