# src/bugbot/core/formatting_v2.py
"""
BugBot v2.0 — Formato de alertas Telegram para MNQ/MES/MGC
"""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
SIDE_EMOJI = {"LONG": "🟩", "SHORT": "🟥"}
CONTRACT_EMOJI = {"MNQ": "📊", "MES": "📈", "MGC": "🥇"}

def fmt_signal(
    symbol:   str,
    signal:   dict,
    risk:     object,
) -> str:
    side     = signal["side"]
    entry    = signal["entry"]
    sl       = signal["sl"]
    zona     = signal["zona"]
    bias     = signal["bias"]
    now      = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M ET")
    emoji    = SIDE_EMOJI.get(side, "⬜")
    c_emoji  = CONTRACT_EMOJI.get(symbol, "📊")

    # TPs
    tp_lines = ""
    total_contracts = sum(tp.contracts for tp in risk.tp_levels) or 1
    for tp in risk.tp_levels:
        pct = tp.contracts / total_contracts
        tp_lines += (
            f"• <b>{tp.name}:</b> <code>{tp.price:,.2f}</code> "
            f"| {int(round(pct*100))}% salida "
            f"| <b>+${tp.profit_usd:,.0f}</b>\n"
    )

    stop_pts = abs(entry - sl)

    return (
        f"{emoji} <b>{side} — {c_emoji} {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Bias:</b> {bias} ✅\n"
        f"<b>Zona:</b> {zona}\n"
        f"<b>Entry:</b> <code>{entry:,.2f}</code>\n"
        f"<b>SL:</b> <code>{sl:,.2f}</code> ({stop_pts:.1f} pts)\n"
        f"<b>Riesgo:</b> ${risk.risk_dollars:,.0f}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{tp_lines}"
        f"━━━━━━━━━━━━━━━━\n"
        f"⚡ BE después de TP1\n"
        f"🕒 <i>{now}</i>"
    )

def fmt_no_signal(symbol: str) -> str:
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M ET")
    return (
        f"😴 <b>{symbol}</b> — Sin señal\n"
        f"🕒 <i>{now}</i>"
    )

def fmt_cycle_start() -> str:
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M ET")
    return f"🟢 <b>BugBot v2.0 iniciado</b> — 🕒 <i>{now}</i>"

def fmt_cycle_end(n_signals: int, duration: int) -> str:
    now = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M ET")
    return (
        f"🟣 <b>Ciclo finalizado</b> "
        f"| 🔔 {n_signals} señales "
        f"| ⏱ {duration}s "
        f"| 🕒 <i>{now}</i>"
    )