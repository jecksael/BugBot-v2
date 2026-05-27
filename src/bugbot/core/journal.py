# src/bugbot/core/journal.py
"""
BugBot v2.0 — Journal automático de señales
Registra cada señal para análisis estadístico posterior
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_PATH = Path("data/journal.json")

def _load() -> list:
    if not JOURNAL_PATH.exists():
        return []
    with open(JOURNAL_PATH, "r") as f:
        return json.load(f)

def _save(entries: list) -> None:
    JOURNAL_PATH.parent.mkdir(exist_ok=True)
    with open(JOURNAL_PATH, "w") as f:
        json.dump(entries, f, indent=2)

def log_signal(
    symbol:      str,
    side:        str,
    entry:       float,
    sl:          float,
    tp1:         float,
    tp2:         float,
    tp3:         float,
    risk_usd:    float,
    zona:        str,
    bias:        str,
    session:     str = "",
) -> dict:
    """
    Registra una señal nueva en el journal.
    Estado inicial: PENDING — tú lo actualizas después.
    """
    entries = _load()

    record = {
        "id":         len(entries) + 1,
        "ts":         datetime.now(timezone.utc).isoformat(),
        "symbol":     symbol,
        "side":       side,
        "entry":      entry,
        "sl":         sl,
        "tp1":        tp1,
        "tp2":        tp2,
        "tp3":        tp3,
        "risk_usd":   risk_usd,
        "zona":       zona,
        "bias":       bias,
        "session":    session,
        "result":     "PENDING",  # WIN / LOSS / PENDING
        "exit_price": None,
        "pnl":        None,
        "notes":      "",
    }

    entries.append(record)
    _save(entries)
    return record

def update_result(
    signal_id:   int,
    result:      str,   # WIN / LOSS
    exit_price:  float,
    notes:       str = "",
) -> dict | None:
    """
    Actualiza el resultado de una señal después de cerrar el trade.
    """
    entries = _load()

    for e in entries:
        if e["id"] == signal_id:
            e["result"]     = result
            e["exit_price"] = exit_price
            e["pnl"]        = round(exit_price - e["entry"], 2) if result == "WIN" else round(e["entry"] - exit_price, 2)
            e["notes"]      = notes
            _save(entries)
            return e

    return None

def get_stats() -> dict:
    """
    Calcula estadísticas del journal.
    """
    entries = _load()
    closed  = [e for e in entries if e["result"] in ("WIN", "LOSS")]

    if not closed:
        return {"message": "Sin trades cerrados aún"}

    wins   = [e for e in closed if e["result"] == "WIN"]
    losses = [e for e in closed if e["result"] == "LOSS"]

    win_rate = len(wins) / len(closed) * 100
    avg_win  = sum(e["pnl"] for e in wins)  / max(len(wins), 1)
    avg_loss = sum(e["pnl"] for e in losses) / max(len(losses), 1)
    total_pnl = sum(e["pnl"] for e in closed)

    # Stats por símbolo
    symbols = {}
    for e in closed:
        sym = e["symbol"]
        if sym not in symbols:
            symbols[sym] = {"wins": 0, "losses": 0}
        if e["result"] == "WIN":
            symbols[sym]["wins"] += 1
        else:
            symbols[sym]["losses"] += 1

    return {
        "total_trades": len(closed),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(win_rate, 1),
        "avg_win":      round(avg_win, 2),
        "avg_loss":     round(avg_loss, 2),
        "total_pnl":    round(total_pnl, 2),
        "by_symbol":    symbols,
    }

def fmt_stats_telegram() -> str:
    """
    Formatea estadísticas para enviar a Telegram.
    """
    s = get_stats()

    if "message" in s:
        return f"📓 <b>Journal</b>\n{s['message']}"

    sym_lines = ""
    for sym, data in s["by_symbol"].items():
        total = data["wins"] + data["losses"]
        wr    = round(data["wins"] / total * 100, 1)
        sym_lines += f"• {sym}: {data['wins']}W / {data['losses']}L ({wr}%)\n"

    return (
        f"📓 <b>Journal BugBot v2.0</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Total trades: <code>{s['total_trades']}</code>\n"
        f"Win Rate:     <code>{s['win_rate']}%</code>\n"
        f"Avg Win:      <code>${s['avg_win']}</code>\n"
        f"Avg Loss:     <code>${s['avg_loss']}</code>\n"
        f"PnL Total:    <code>${s['total_pnl']}</code>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Por contrato:</b>\n"
        f"{sym_lines}"
    )
def fmt_pending_telegram() -> str:
    """
    Muestra señales pendientes de actualizar.
    """
    entries = _load()
    pending = [e for e in entries if e["result"] == "PENDING"]

    if not pending:
        return "📓 <b>Journal</b>\nSin señales pendientes."

    lines = ""
    for e in pending:
        lines += (
            f"━━━━━━━━━━━━━━━━\n"
            f"<b>#{e['id']} {e['symbol']} {e['side']}</b>\n"
            f"Entry: <code>{e['entry']}</code>\n"
            f"SL:    <code>{e['sl']}</code>\n"
            f"TP1:   <code>{e['tp1']}</code>\n"
            f"TP2:   <code>{e['tp2']}</code>\n"
            f"TP3:   <code>{e['tp3']}</code>\n"
            f"Riesgo: <code>${e['risk_usd']}</code>\n"
            f"🕒 {e['ts'][:16]}\n"
            f"Para actualizar:\n"
            f"<code>/update {e['id']} WIN 00000</code>\n"
            f"<code>/update {e['id']} LOSS 00000</code>\n"
        )

    return f"📓 <b>Señales Pendientes</b>\n{lines}"