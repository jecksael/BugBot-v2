# src/bugbot/core/engine.py
"""
BugBot v2.0 — Engine principal para MNQ/MES/MGC
Ahora con observabilidad: cada descarte loggea el motivo y nº de velas.
Estrategia: SMC (CHoCH/BOS + liquidity sweep + MACD).
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from ..core.journal import log_signal
from ..adapters.data import fetch_ohlcv
from ..config.settings import get_settings
from ..core.risk import calculate_contracts
from ..core.strategy_smc import detect_signal
from ..core.formatting_v2 import fmt_signal
from ..core.confluences import compute_confluences

log = logging.getLogger("bugbot.engine")


def analyze() -> list[dict]:
    s = get_settings()
    signals: list[dict] = []

    log.info("cycle start | symbols=%s tf=%s", s.symbols, s.timeframe)

    for symbol in s.symbols:
        try:
            # 1. Datos
            df = fetch_ohlcv(symbol, timeframe=s.timeframe, bars=200)
            df.attrs["symbol"] = symbol
            log.info("%s | velas=%d last_close=%.2f", symbol, len(df), df["close"].iloc[-1])

            # 2. Señal SMC (devuelve siempre dict con ok + reason)
            sig = detect_signal(df)
            if not sig["ok"]:
                log.info("%s | sin señal: %s", symbol, sig["reason"])
                continue

            log.info("%s | SETUP %s %s @ %.2f sl=%.2f (%s)",
                     symbol, sig["side"], sig["event"], sig["entry"], sig["sl"], sig["zona"])

            # 3. Riesgo
            risk = calculate_contracts(
                symbol=symbol,
                account_size=s.account_size,
                entry=sig["entry"],
                stop=sig["sl"],
                side=sig["side"],
            )
            if not risk.viable:
                log.info("%s | descartado por riesgo: %s", symbol, risk.reason)
                continue

            # 3.5 Confluencias — NUNCA debe bloquear ni cambiar la señal real.
            try:
                confluences = compute_confluences(df, sig, symbol, s.timeframe)
            except Exception:
                log.exception("%s | error calculando confluencias (no crítico)", symbol)
                confluences = []
            sig["confluences"] = confluences

            # 4. Journal
            log_signal(
                symbol      = symbol,
                side        = sig["side"],
                entry       = sig["entry"],
                sl          = sig["sl"],
                tp1         = risk.tp_levels[0].price,
                tp2         = risk.tp_levels[1].price,
                tp3         = risk.tp_levels[2].price,
                risk_usd    = risk.risk_dollars,
                zona        = sig["zona"],
                bias        = sig["bias"],
                session     = sig.get("session") or ("NY" if symbol in ["MNQ", "MES"] else "ASIA"),
                confluences = confluences,
            )

            # 5. Mensaje
            text = fmt_signal(symbol, sig, risk)
            signals.append({"text": text, "parse_mode": "HTML", "signals_count": 1})
            log.info("%s | ✅ señal emitida", symbol)

        except Exception as e:
            log.exception("%s | error en análisis", symbol)
            signals.append({
                "text":          f"⚠️ Error en {symbol}: {e}",
                "parse_mode":    None,
                "signals_count": 0,
            })

    log.info("cycle end | señales=%d", sum(x["signals_count"] for x in signals))
    return signals
