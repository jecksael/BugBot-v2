# src/bugbot/cli/run_bot.py
"""
BugBot v2.0 — Bot principal con ciclo automático
"""
from __future__ import annotations
import time
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..core.engine import analyze
from ..core.formatting_v2 import fmt_cycle_start, fmt_cycle_end

BUSY = False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 BugBot v2.0 activo\n"
        "Contratos: MNQ | MES | MGC\n"
        "Usa /scan para analizar ahora mismo."
    )

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔍 Analizando mercado...")
    await _run_cycle(context)

async def _run_cycle(context: ContextTypes.DEFAULT_TYPE) -> None:
    global BUSY
    if BUSY:
        return
    BUSY = True

    s = get_settings()
    started = time.monotonic()

    try:
        await context.bot.send_message(
            chat_id=s.chat_id,
            text=fmt_cycle_start(),
            parse_mode="HTML",
            message_thread_id=s.thread_id if s.thread_id else None,
        )

        signals = analyze()
        total   = 0

        for msg in signals:
            await context.bot.send_message(
                chat_id=s.chat_id,
                text=msg["text"],
                parse_mode=msg.get("parse_mode"),
                message_thread_id=s.thread_id if s.thread_id else None,
            )
            total += msg.get("signals_count", 0)

        duration = int(time.monotonic() - started)

        await context.bot.send_message(
            chat_id=s.chat_id,
            text=fmt_cycle_end(total, duration),
            parse_mode="HTML",
            message_thread_id=s.thread_id if s.thread_id else None,
        )

    finally:
        BUSY = False

async def cycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_cycle(context)

def main() -> None:
    setup_logging()
    s = get_settings()

    app = Application.builder().token(s.bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))

    # Ciclo automático
    app.job_queue.run_repeating(
        cycle_job,
        interval=s.polling_interval_seconds,
        first=10,
    )

    print("🚀 BugBot v2.0 corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()