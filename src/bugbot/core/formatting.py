from __future__ import annotations
from datetime import datetime

def cycle_started() -> str:
    return "🟢 BOT iniciado"

def cycle_finished(duration_s: int, n_alerts: int) -> str:
    return f"🟣 Ciclo finalizado · ⏱️ {duration_s}s · 🔔 {n_alerts} alertas"

def fmt_time_utc(ts: datetime) -> str:
        hhmm = ts.strftime("%H:%M")   # ← sin emoji aquí
        return f"🕒 <i>{hhmm} UTC</i>"

def _fmt_price(x: float) -> str:
    s = f"{x:,.2f}".replace(",", " ")
    s = s.rstrip("0").rstrip(".")
    return s

def _side_emoji(side: str) -> str:
    return "🟩" if side.upper() == "LONG" else "🟥"

def _fmt_bars_ago(n: int) -> str:
    n = int(n)
    word = "vela" if n == 1 else "velas"
    return f"{n} {word} atrás"


def signal_block_html(sig: dict) -> str:
    sl_label = "SL"
    if sig.get("sl_source") == "fractal":
        sl_label = "SL (fractal)"

    tps_lines = "\n".join(
        [f"• <b>TP{i+1}:</b> <code>{_fmt_price(tp)}</code>" for i, tp in enumerate(sig["tps"])]
    )

    fractal_line = ""
    fractal = sig.get("fractals")
    if fractal:
        emoji = "🔻" if fractal.get("type") == "bearish" else "🔺"
        risk = sig.get("risk_pct")
        risk_txt = f" · riesgo {risk * 100:.2f}%" if isinstance(risk, (int, float)) else ""
        fractal_line = (
            f"\n<b>Fractal:</b> {emoji} <code>{_fmt_price(fractal['price'])}</code> · "
            f"{_fmt_bars_ago(fractal.get('bars_ago', 0))}{risk_txt}"
        )

    return (
        f"<b>{_side_emoji(sig['side'])} {sig['side'].upper()} — {sig['symbol']} · {sig['tf']}</b>\n"
        f"<b>Entry:</b> <code>{_fmt_price(sig['entry_lo'])}–{_fmt_price(sig['entry_hi'])}</code>\n"
        f"<b>{sl_label}:</b> <code>{_fmt_price(sig['sl'])}</code>\n"
        f"{tps_lines}"
        f"{fractal_line}"
    )

def signals_digest_html(signals: list[dict], note: str | None, ts: datetime) -> str:
    header = f"📊 <b>{len(signals)} señales detectadas</b>\n"
    blocks = "\n━━━━━━━━━━━━━━━━\n".join([signal_block_html(s) for s in signals])
    footer = f"\n📰 <b>Contexto:</b> {note}" if note else ""
    return header + blocks + footer + f"\n{fmt_time_utc(ts)}"
