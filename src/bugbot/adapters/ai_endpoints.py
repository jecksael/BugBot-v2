"""
BugBot — Endpoints de IA para prospeccion.html (Mensajes + Lista de 100)
=========================================================================
Router de FastAPI aparte, pensado para montarse en la MISMA app que ya
corre en Railway (src/bugbot/adapters/webhook.py). No toca nada de
trading — vive en su propio archivo para no mezclar responsabilidades.

Expone:
  POST /ai/draft-message   -> redacta un mensaje de WhatsApp con el
                              contexto real del prospecto (etapa,
                              historial, fuente, categoría pedida)
  POST /ai/calificar-l100  -> lee una nota libre sobre un contacto y
                              devuelve las 16 casillas de calificación
                              de la Lista de 100 (Core/Biz/Trigger)

Seguridad: exige un token compartido en el header `X-AI-Token`
(AI_SHARED_SECRET). No es una key real de nada — solo evita que
cualquiera que encuentre la URL use tu cuota de IA. El navegador
manda este token desde prospeccion.html (Config → Asistente de IA),
así que no es un secreto perfecto, pero alcanza para un uso personal.

Ver README_INSTRUCCIONES.md en esta misma carpeta para cómo instalar
esto en tu repo real y qué variables de entorno agregar en Railway.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx
from fastapi import APIRouter, Header, HTTPException

log = logging.getLogger("bugbot.ai")
router = APIRouter(prefix="/ai", tags=["ai"])

# ─── Config (variables de entorno, Railway → tu servicio → Variables) ───
AI_SHARED_SECRET = os.getenv("AI_SHARED_SECRET", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic").lower()  # "anthropic" | "openai"
AI_MODEL = os.getenv("AI_MODEL", "")  # si lo dejas vacío, usa el default de abajo

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5"  # confirmá/actualizá en docs.claude.com/en/docs/about-claude/models

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"


def _check_token(x_ai_token: str | None) -> None:
    if not AI_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="AI_SHARED_SECRET no configurado en el servidor")
    if x_ai_token != AI_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="token inválido")


async def call_llm(system: str, user: str, max_tokens: int = 500) -> str:
    """Llama al proveedor configurado (AI_PROVIDER) y devuelve el texto plano de la respuesta."""
    if AI_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY no configurado")
        model = AI_MODEL or OPENAI_DEFAULT_MODEL
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        if r.status_code >= 400:
            log.error("OpenAI error %s: %s", r.status_code, r.text[:500])
            raise HTTPException(status_code=502, detail=f"error de OpenAI: {r.text[:300]}")
        data = r.json()
        return data["choices"][0]["message"]["content"]

    # default: anthropic
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurado")
    model = AI_MODEL or ANTHROPIC_DEFAULT_MODEL
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
    if r.status_code >= 400:
        log.error("Anthropic error %s: %s", r.status_code, r.text[:500])
        raise HTTPException(status_code=502, detail=f"error de Anthropic: {r.text[:300]}")
    data = r.json()
    return data["content"][0]["text"]


def _extract_json(text: str) -> dict:
    """El modelo a veces envuelve el JSON en ```json ... ``` pese a la instrucción de no hacerlo."""
    t = text.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    return json.loads(t)


# ───────────────────────── /ai/draft-message ─────────────────────────

DRAFT_SYSTEM = (
    "Sos el asistente de redacción de Dionar, agente de seguros de vida (HGI/Integrity, "
    "productos IUL) que prospecta por WhatsApp en español, tono cálido y cercano, sin sonar "
    "a vendedor de guion. Nunca uses emojis en exceso (máximo 1-2), nunca inventes datos que "
    "no te dieron (montos, citas, promesas de rendimiento). Escribí UN SOLO mensaje de WhatsApp, "
    "listo para pegar y enviar tal cual, sin comillas ni explicación alrededor, dirigido a la "
    "persona por su nombre real (nunca un placeholder tipo {nombre})."
)


@router.post("/draft-message")
async def draft_message(payload: dict, x_ai_token: str | None = Header(default=None, alias="X-AI-Token")):
    _check_token(x_ai_token)
    nombre = str(payload.get("nombre", "")).strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="falta 'nombre'")
    categoria = str(payload.get("categoria", "")).strip() or "Seguimiento"
    etapa = str(payload.get("etapa", "")).strip()
    fuente = str(payload.get("fuente", "")).strip()
    nota = str(payload.get("nota", "")).strip()
    motivo = str(payload.get("motivoNoInteresado", "")).strip()
    historial = payload.get("historial") or []

    hist_txt = "\n".join(
        f"- {h.get('fecha', '?')}: {h.get('texto', '')}" for h in historial[-6:]
    ) or "(sin conversación previa registrada)"

    user_prompt = (
        f"Prospecto: {nombre}\n"
        f"Etapa actual del CRM: {etapa or 'sin etapa'}\n"
        f"Cómo lo conoció / fuente: {fuente or 'sin especificar'}\n"
        f"Categoría de mensaje pedida: {categoria}\n"
        f"Nota general: {nota or '—'}\n"
        f"Motivo si está marcado 'No interesado': {motivo or '—'}\n\n"
        f"Historial de conversación reciente (orden cronológico):\n{hist_txt}\n\n"
        f"Escribí el mensaje de WhatsApp para esta categoría, coherente con lo que ya se hablaron."
    )

    texto = await call_llm(DRAFT_SYSTEM, user_prompt, max_tokens=400)
    return {"mensaje": texto.strip()}


# ───────────────────────── /ai/calificar-l100 ─────────────────────────

L100_CORE = ["Edad +25", "Casado", "Hijos", "EAD y Social", "U.S Resident", "Bank Account"]
L100_BIZ = ["High Income", "Business Mindset", "People Skills", "Coachable", "Tech Savvy"]
L100_TRIG = ["Actively Looking", "Dissatisfied", "Open To New Streams", "Investments", "MLM"]

_SCHEMA_EXAMPLE = json.dumps(
    {
        "core": {q: "true/false" for q in L100_CORE},
        "biz": {q: "true/false" for q in L100_BIZ},
        "trig": {q: "true/false" for q in L100_TRIG},
    },
    ensure_ascii=False,
)

CALIFICAR_SYSTEM = (
    "Calificás contactos para la Lista de 100 de un agente de seguros de vida (HGI/IUL). "
    "A partir de una descripción libre en español, decidís qué tan probable es cada afirmación "
    "para esa persona, SOLO basándote en lo que el texto dice o implica razonablemente — si no "
    "hay información para una afirmación, la dejás en false, no inventes. Respondé ÚNICAMENTE "
    "con JSON válido, sin texto adicional, sin backticks, con exactamente esta forma "
    "(reemplazando \"true/false\" por valores booleanos reales):\n" + _SCHEMA_EXAMPLE
)


@router.post("/calificar-l100")
async def calificar_l100(payload: dict, x_ai_token: str | None = Header(default=None, alias="X-AI-Token")):
    _check_token(x_ai_token)
    nota = str(payload.get("nota", "")).strip()
    if not nota:
        raise HTTPException(status_code=422, detail="falta 'nota'")

    texto = await call_llm(CALIFICAR_SYSTEM, nota, max_tokens=400)
    try:
        data = _extract_json(texto)
    except Exception:
        log.error("respuesta no-JSON del modelo: %s", texto[:300])
        raise HTTPException(status_code=502, detail="el modelo no devolvió JSON válido, probá de nuevo")

    # nos aseguramos de que las 16 claves existan aunque el modelo omita alguna
    core = {q: bool(data.get("core", {}).get(q, False)) for q in L100_CORE}
    biz = {q: bool(data.get("biz", {}).get(q, False)) for q in L100_BIZ}
    trig = {q: bool(data.get("trig", {}).get(q, False)) for q in L100_TRIG}
    return {"core": core, "biz": biz, "trig": trig}
