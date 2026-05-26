# src/bugbot/config/settings.py
"""
BugBot v2.0 — Settings para futuros de índices (NQ / MES)
"""
from __future__ import annotations
from dataclasses import dataclass
from dotenv import load_dotenv
import os

load_dotenv()

def _csv(s: str | None) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]

def _csv_float(s: str | None) -> list[float]:
    vals: list[float] = []
    for x in _csv(s):
        try:
            vals.append(float(x))
        except ValueError:
            pass
    return vals

@dataclass(frozen=True)
class Settings:
    # Telegram
    bot_token:                  str
    chat_id:                    int
    thread_id:                  int | None
    env:                        str
    log_level:                  str
    timezone:                   str
    polling_interval_seconds:   int

    # Símbolos y timeframe
    symbols:                    list[str]
    timeframe:                  str

    # EMAs
    ema_fast:                   int
    ema_slow:                   int

    # Risk Management v2.0
    account_size:               float
    risk_pct:                   float
    default_stop_points:        float
    apex_account:               float

    # Fuente de datos
    data_source:                str
    csv_path:                   str

def get_settings() -> Settings:
    token      = os.getenv("BOT_TOKEN", "")
    chat_id    = os.getenv("TARGET_CHAT_ID", "")

    if not token or not chat_id:
        raise RuntimeError("Faltan BOT_TOKEN o TARGET_CHAT_ID en .env")

    return Settings(
        bot_token                = token,
        chat_id                  = int(chat_id),
        thread_id                = int(os.getenv("TELEGRAM_THREAD_ID")) if os.getenv("TELEGRAM_THREAD_ID") else None,
        env                      = os.getenv("ENV", "dev"),
        log_level                = os.getenv("LOG_LEVEL", "INFO"),
        timezone                 = os.getenv("TIMEZONE", "America/Denver"),
        polling_interval_seconds = int(os.getenv("POLLING_INTERVAL_SECONDS", "60")),

        symbols                  = _csv(os.getenv("SYMBOLS") or "NQ,MES"),
        timeframe                = os.getenv("TIMEFRAME", "5m"),

        ema_fast                 = int(os.getenv("EMA_FAST", "21")),
        ema_slow                 = int(os.getenv("EMA_SLOW", "52")),

        account_size             = float(os.getenv("ACCOUNT_SIZE", "50000")),
        risk_pct                 = float(os.getenv("RISK_PCT", "0.006")),
        default_stop_points      = float(os.getenv("DEFAULT_STOP_POINTS", "15")),
        apex_account             = float(os.getenv("APEX_ACCOUNT", "50000")),

        data_source              = os.getenv("DATA_SOURCE", "csv"),
        csv_path                 = os.getenv("CSV_PATH", "data/"),
    )