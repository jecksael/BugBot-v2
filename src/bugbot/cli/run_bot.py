from __future__ import annotations
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..core import engine
from ..core import formatting as fmt

BUSY = False  # evita solapamiento de ciclos

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 BUG listo. Usa /testgrupo para probar envío al GRUPO.\n"
        "El ciclo automático está activo."
    )

async def testgrupo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = get_settings()
    await context.bot.send_message(
        chat_id=s.chat_id,
        text="BUG: test desde /testgrupo ✅",
        message_thread_id=s.thread_id if s.thread_id is not None else None,
    )
    await update.message.reply_text("Enviado al grupo ✅")

async def cycle_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    global BUSY
    if BUSY:
        return
    BUSY = True
    try:
        s = get_settings()
        started = time.monotonic()

        await context.bot.send_message(
            chat_id=s.chat_id,
            text=fmt.cycle_started(),
            message_thread_id=s.thread_id if s.thread_id is not None else None,
        )

        alerts = engine.analyze()

        total_signals = 0
        for msg in alerts:
            total_signals += int(msg.get("signals_count", 1))
            await context.bot.send_message(
                chat_id=s.chat_id,
                text=msg["text"],
                parse_mode=msg.get("parse_mode"),
                message_thread_id=s.thread_id if s.thread_id is not None else None,
            )

        elapsed = int(time.monotonic() - started)
        await context.bot.send_message(
            chat_id=s.chat_id,
            text=fmt.cycle_finished(elapsed, total_signals),
            message_thread_id=s.thread_id if s.thread_id is not None else None,
        )
    finally:
        BUSY = False

def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)

    app = Application.builder().token(s.bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testgrupo", testgrupo))

    # Agenda el ciclo automático con el JobQueue de PTB
    app.job_queue.run_repeating(
        cycle_job,
        interval=s.polling_interval_seconds,
        first=5,   # arranca 5s después de iniciar
        name="bug_cycle",
    )

    app.run_polling()

if __name__ == "__main__":
    main()
