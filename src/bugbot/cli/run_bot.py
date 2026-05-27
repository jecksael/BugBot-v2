# src/bugbot/cli/run_bot.py
"""
BugBot v2.0 — Bot principal con ciclo automático
"""
from __future__ import annotations
import time
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from ..core.journal import fmt_stats_telegram
from ..core.journal import fmt_stats_telegram, fmt_pending_telegram, update_result
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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = fmt_stats_telegram()
    await update.message.reply_text(text, parse_mode="HTML")

async def journal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = fmt_pending_telegram()
    await update.message.reply_text(text, parse_mode="HTML")

async def update_trade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Uso: /update ID WIN/LOSS PRECIO_SALIDA
    Ejemplo: /update 1 WIN 21045
    """
    try:
        args        = context.args
        signal_id   = int(args[0])
        result      = args[1].upper()
        exit_price  = float(args[2])

        if result not in ("WIN", "LOSS"):
            await update.message.reply_text("❌ Usa WIN o LOSS")
            return

        record = update_result(signal_id, result, exit_price)

        if not record:
            await update.message.reply_text(f"❌ Señal #{signal_id} no encontrada")
            return

        emoji = "✅" if result == "WIN" else "❌"
        await update.message.reply_text(
            f"{emoji} <b>Señal #{signal_id} actualizada</b>\n"
            f"Resultado: <b>{result}</b>\n"
            f"Salida: <code>{exit_price}</code>\n"
            f"PnL: <code>{record['pnl']} pts</code>",
            parse_mode="HTML"
        )

    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ Formato incorrecto\n"
            "Usa: <code>/update ID WIN/LOSS PRECIO</code>\n"
            "Ejemplo: <code>/update 1 WIN 21045</code>",
            parse_mode="HTML"
        )

async def _run_cycle(context: ContextTypes.DEFAULT_TYPE) -> None:
    global BUSY
    if BUSY:
        return
    BUSY = True

    s = get_settings()
    started = time.monotonic()

    try:
        signals = analyze()
        total   = sum(msg.get("signals_count", 0) for msg in signals)

        # Solo mandar mensajes si hay señales
        if total > 0:
            for msg in signals:
                await context.bot.send_message(
                    chat_id=s.chat_id,
                    text=msg["text"],
                    parse_mode=msg.get("parse_mode"),
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
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("journal", journal))
    app.add_handler(CommandHandler("update", update_trade))

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