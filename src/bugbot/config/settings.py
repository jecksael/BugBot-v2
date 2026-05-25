from __future__ import annotations
from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

def _csv(s: str | None) -> list[str]:
    """Convierte 'a,b,c' -> ['a','b','c'] (trim) y maneja None."""
    return [x.strip() for x in (s or "").split(",") if x.strip()]

def _csv_float(s: str | None) -> list[float]:
    """Convierte '0.01,0.02' -> [0.01, 0.02] (ignora valores inválidos)."""
    vals: list[float] = []
    for x in _csv(s):
        try:
            vals.append(float(x))
        except ValueError:
            pass
    return vals

@dataclass(frozen=True)
class Settings:
    bot_token: str
    chat_id: int
    thread_id: int | None
    env: str
    log_level: str
    timezone: str
    polling_interval_seconds: int

    # exchange / symbols
    exchanges: list[str]
    symbols: list[str]

    # strategy
    timeframe: str
    ema_fast: int
    ema_slow: int
    tp_pcts: list[float]
    sl_pct: float
    use_fractal_filter: bool
    fractal_lookback: int

def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "")
    chat_id_str = os.getenv("TARGET_CHAT_ID", "")

    if not token or not chat_id_str:
        raise RuntimeError("Faltan BOT_TOKEN o TARGET_CHAT_ID en .env")

    return Settings(
        bot_token=token,
        chat_id=int(chat_id_str),
        thread_id=int(os.getenv("TELEGRAM_THREAD_ID")) if os.getenv("TELEGRAM_THREAD_ID") else None,
        env=os.getenv("ENV", "dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "UTC"),
        polling_interval_seconds=int(os.getenv("POLLING_INTERVAL_SECONDS", "60")),

        exchanges=_csv(os.getenv("EXCHANGES") or "binance"),
        symbols=_csv(os.getenv("SYMBOLS") or "BTC/USDT"),

        timeframe=os.getenv("TIMEFRAME", "1H").upper(),
        ema_fast=int(os.getenv("EMA_FAST", "21")),
        ema_slow=int(os.getenv("EMA_SLOW", "52")),
        tp_pcts=_csv_float(os.getenv("TP_PCTS") or "0.006,0.01,0.015"),
        sl_pct=float(os.getenv("SL_PCT", "0.007")),
        use_fractal_filter=os.getenv("USE_FRACTAL_FILTER", "1").strip() not in ("0", "false", "False"),
        fractal_lookback=int(os.getenv("FRACTAL_LOOKBACK", "5")),
    )
