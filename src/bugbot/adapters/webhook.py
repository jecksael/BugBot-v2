# src/bugbot/adapters/webhook.py
"""
BugBot v2.0 — Webhook receiver para alertas de TradingView (LuxAlgo SMC)

Reemplaza el polling de 300s: TradingView evalúa la estrategia en sus
servidores y empuja la señal aquí al cierre de vela. El chart NO necesita
estar abierto; este endpoint SÍ debe estar siempre online (→ VPS Hostinger).

Flujo:
  TradingView alert (JSON)  →  POST /webhook/tv
    → valida token secreto
    → normaliza payload
    → Risk Engine (calculate_contracts)
    → log_signal (journal)
    → send_text (Telegram)

Arranque (dev):
    uvicorn bugbot.adapters.webhook:app --host 0.0.0.0 --port 8000

Arranque (prod, detrás de HTTPS — ver notas al final):
    uvicorn bugbot.adapters.webhook:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations
import logging
import os

from fastapi import FastAPI, Request, HTTPException

from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..core.risk import calculate_contracts, CONTRACT_SPECS
from ..core.journal import log_signal
from ..core.formatting_v2 import fmt_signal
from ..adapters.telegram import send_text

setup_logging()
log = logging.getLogger("bugbot.webhook")

app = FastAPI(title="BugBot v2.0 Webhook", version="2.0")

# Token secreto compartido con TradingView. Va en el payload del alert,
# NO en la URL (la URL puede quedar en logs/historial).
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

VALID_SYMBOLS = {"MNQ", "MES", "MGC"}
VALID_SIDES   = {"LONG", "SHORT"}


@app.get("/health")
def health():
    """Para que el VPS / uptime monitor confirme que está vivo."""
    return {"status": "ok", "service": "bugbot-webhook"}


@app.post("/webhook/tv")
async def tradingview_webhook(request: Request):
    # 1. Parsear JSON crudo (TradingView manda text/plain a veces)
    try:
        payload = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", "ignore")
        log.warning("payload no-JSON recibido: %s", raw[:200])
        raise HTTPException(status_code=400, detail="payload no es JSON válido")

    # 2. Autenticación por token (rechaza señales falsas)
    if not WEBHOOK_SECRET:
        log.error("WEBHOOK_SECRET no configurado en .env — rechazando todo")
        raise HTTPException(status_code=500, detail="servidor sin secret configurado")
    if payload.get("secret") != WEBHOOK_SECRET:
        log.warning("token inválido desde %s", request.client.host if request.client else "?")
        raise HTTPException(status_code=401, detail="token inválido")

    # 3. Normalizar y validar campos
    try:
        symbol = str(payload["symbol"]).upper().strip()
        side   = str(payload["side"]).upper().strip()
        entry  = float(payload["entry"])
        # SL opcional: si no viene o es igual al entry (ej. {{close}}),
        # lo calcula el bot con el default_stop del símbolo.
        raw_sl = payload.get("sl")
        if raw_sl is None or float(raw_sl) == entry:
            stop_pts = CONTRACT_SPECS[symbol]["default_stop"]
            sl = entry - stop_pts if side == "LONG" else entry + stop_pts
        else:
            sl = float(raw_sl)
    except (KeyError, ValueError, TypeError) as e:
        log.warning("payload incompleto/ inválido: %s | %s", payload, e)
        raise HTTPException(status_code=422, detail=f"campos faltantes o inválidos: {e}")

    if symbol not in VALID_SYMBOLS:
        raise HTTPException(status_code=422, detail=f"símbolo no soportado: {symbol}")
    if side not in VALID_SIDES:
        raise HTTPException(status_code=422, detail=f"side no soportado: {side}")

    # Campos opcionales de contexto SMC desde LuxAlgo
    zona = str(payload.get("zona", payload.get("event", "TV"))).upper()
    bias = str(payload.get("bias", side)).upper()

    s = get_settings()
    log.info("ALERT %s %s entry=%.2f sl=%.2f zona=%s", symbol, side, entry, sl, zona)

    # 4. Risk Engine
    try:
        risk = calculate_contracts(
            symbol=symbol,
            account_size=s.account_size,
            entry=entry,
            stop=sl,
            side=side,
        )
    except Exception as e:
        log.exception("error en risk engine")
        raise HTTPException(status_code=500, detail=f"risk engine: {e}")

    if not risk.viable:
        log.info("%s | descartado por riesgo: %s", symbol, risk.reason)
        # Avisamos pero devolvemos 200: el alert llegó bien, solo no operamos.
        send_text(f"⚠️ {symbol} {side} descartado — {risk.reason}")
        return {"status": "skipped", "reason": risk.reason}

    # 5. Journal
    sig = {
        "side": side, "entry": entry, "sl": sl,
        "zona": zona, "bias": bias, "event": zona,
    }
    log_signal(
        symbol=symbol, side=side, entry=entry, sl=sl,
        tp1=risk.tp_levels[0].price,
        tp2=risk.tp_levels[1].price,
        tp3=risk.tp_levels[2].price,
        risk_usd=risk.risk_dollars,
        zona=zona, bias=bias,
        session="TV",
    )

    # 6. Telegram
    text = fmt_signal(symbol, sig, risk)
    send_text(text, parse_mode="HTML")
    log.info("%s | ✅ señal emitida vía webhook", symbol)

    return {"status": "ok", "symbol": symbol, "side": side}
