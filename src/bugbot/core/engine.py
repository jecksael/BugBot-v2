# src/bugbot/core/engine.py
"""
BugBot v2.0 — Engine principal para MNQ/MES/MGC
"""
from __future__ import annotations
from datetime import datetime, timezone

from ..adapters.data import fetch_ohlcv
from ..config.settings import get_settings
from ..core.risk import calculate_contracts
from ..core.strategy_v2 import detect_signal, add_emas, add_vwap, add_volume_sma
from ..core.formatting_v2 import fmt_signal, fmt_no_signal

def analyze() -> list[dict]:
    s = get_settings()
    signals = []

    for symbol in s.symbols:
        try:
            # 1. Obtener datos
            df = fetch_ohlcv(symbol, timeframe=s.timeframe, bars=200)

            # 2. Agregar indicadores
            df = add_emas(df)
            df = add_vwap(df)
            df = add_volume_sma(df)

            # 3. Detectar señal
            signal = detect_signal(df)

            if not signal:
                continue

            # 4. Calcular riesgo
            risk = calculate_contracts(
                symbol=symbol,
                account_size=s.account_size,
                entry=signal["entry"],
                stop=signal["sl"],
                side=signal["side"],
            )

            if not risk.viable:
                continue

            # 5. Formatear mensaje
            text = fmt_signal(symbol, signal, risk)

            signals.append({
                "text":          text,
                "parse_mode":    "HTML",
                "signals_count": 1,
            })

        except Exception as e:
            signals.append({
                "text":          f"⚠️ Error en {symbol}: {e}",
                "parse_mode":    None,
                "signals_count": 0,
            })

    return signals