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
import random
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


def _temperature_rejected(status: int, body: str) -> bool:
    """Algunos modelos (ej. modelos de razonamiento más nuevos) rechazan el parámetro
    `temperature` directamente ("`temperature` is deprecated for this model" en Anthropic).
    Esto es un guard preventivo: si el proveedor lo rechaza por cualquier variante de este
    motivo, reintentamos una vez sin mandar `temperature`, en vez de romper la función."""
    if status not in (400, 422):
        return False
    return "temperature" in body.lower() and (
        "deprecated" in body.lower() or "not supported" in body.lower() or "unsupported" in body.lower()
    )


async def call_llm(system: str, user: str, max_tokens: int = 500, temperature: float = 0.9) -> str:
    """Llama al proveedor configurado (AI_PROVIDER) y devuelve el texto plano de la respuesta.

    temperature: qué tan variada/creativa es la salida. Bajo (~0.2) para tareas de
    clasificación/extracción donde querés consistencia; alto (~0.9-1.0) para redacción
    donde querés variedad entre llamadas sucesivas para el mismo prospecto. Si el modelo
    configurado no acepta este parámetro, se reintenta automáticamente sin él (ver
    _temperature_rejected) — así el feature de variedad no rompe el resto del endpoint
    si Anthropic/OpenAI cambian qué modelos aceptan `temperature`.
    """
    if AI_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY no configurado")
        model = AI_MODEL or OPENAI_DEFAULT_MODEL
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
            if r.status_code >= 400 and _temperature_rejected(r.status_code, r.text):
                log.warning("OpenAI rechazó 'temperature', reintentando sin ese parámetro")
                payload.pop("temperature", None)
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
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
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        if r.status_code >= 400 and _temperature_rejected(r.status_code, r.text):
            log.warning("Anthropic rechazó 'temperature' para el modelo %s, reintentando sin ese parámetro", model)
            payload.pop("temperature", None)
            r = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    if r.status_code >= 400:
        log.error("Anthropic error %s: %s", r.status_code, r.text[:500])
        raise HTTPException(status_code=502, detail=f"error de Anthropic: {r.text[:300]}")
    data = r.json()
    # data["content"] es una LISTA de bloques, no siempre el primero es el texto: los modelos con
    # razonamiento extendido devuelven bloques de tipo "thinking"/"redacted_thinking" ANTES del
    # bloque de tipo "text" (esto es lo que rompía con KeyError: 'text' cuando el modelo decidía
    # razonar, algo más probable cuanto más se le pide en el prompt que piense paso a paso). Acá
    # juntamos todos los bloques de texto reales e ignoramos cualquier bloque de razonamiento.
    text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    if not text_blocks:
        log.error("Anthropic no devolvió ningún bloque de texto: %s", json.dumps(data)[:500])
        raise HTTPException(status_code=502, detail="Anthropic no devolvió texto (solo razonamiento?) — probá de nuevo")
    return "\n".join(text_blocks).strip()


def _extract_json(text: str) -> dict:
    """El modelo a veces envuelve el JSON en ```json ... ``` pese a la instrucción de no hacerlo,
    y en /calificar-l100 le pedimos a propósito un breve razonamiento ANTES del JSON (mejora la
    calibración de las respuestas) — así que nos quedamos con el primer bloque {...} que aparezca,
    en vez de asumir que toda la respuesta es JSON."""
    t = text.strip()
    t = re.sub(r"^```(json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    match = re.search(r"\{.*\}", t, re.S)
    if match:
        t = match.group(0)
    return json.loads(t)


# ───────────────────────── /ai/draft-message ─────────────────────────

DRAFT_SYSTEM = (
    "Sos el asistente de redacción de Dionar, agente de seguros de vida (HGI/Integrity, "
    "productos IUL) que prospecta por WhatsApp en español, tono cálido y cercano, sin sonar "
    "a vendedor de guion. Nunca uses emojis en exceso (máximo 1-2), nunca inventes datos que "
    "no te dieron (montos, citas, promesas de rendimiento). Escribí UN SOLO mensaje de WhatsApp, "
    "listo para pegar y enviar tal cual, sin comillas ni explicación alrededor, dirigido a la "
    "persona por su nombre real (nunca un placeholder tipo {nombre}).\n\n"
    "Te van a dar una plantilla de referencia (título + texto) que Dionar eligió para este envío. "
    "Esa plantilla define el ÁNGULO y el TEMA del mensaje — tu trabajo es escribir una versión "
    "nueva y personalizada de ESE mismo ángulo/tema, adaptada al prospecto real (su etapa, "
    "fuente, notas e historial), NUNCA copiar la plantilla literal ni cambiar de tema. Si no te "
    "dan una plantilla específica, usá la categoría general como guía de tono/objetivo. Variá la "
    "redacción (apertura, orden de las ideas, palabras) cada vez que te pidan un mensaje para el "
    "mismo prospecto, incluso si la plantilla es la misma — no repitas la misma frase de apertura."
)


_OPENING_STYLES = [
    "empezá saludando y preguntando cómo está",
    "empezá yendo directo al tema, sin vuelta",
    "empezá con una observación genuina sobre su situación",
    "empezá recordándole brevemente de qué se conocen",
    "empezá con una pregunta abierta relacionada al tema",
]


@router.post("/draft-message")
async def draft_message(payload: dict, x_ai_token: str | None = Header(default=None, alias="X-AI-Token")):
    _check_token(x_ai_token)
    nombre = str(payload.get("nombre", "")).strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="falta 'nombre'")
    categoria = str(payload.get("categoria", "")).strip() or "Seguimiento"
    plantilla_titulo = str(payload.get("plantillaTitulo", "")).strip()
    plantilla_texto = str(payload.get("plantillaTexto", "")).strip()
    etapa = str(payload.get("etapa", "")).strip()
    fuente = str(payload.get("fuente", "")).strip()
    nota = str(payload.get("nota", "")).strip()
    motivo = str(payload.get("motivoNoInteresado", "")).strip()
    historial = payload.get("historial") or []

    hist_txt = "\n".join(
        f"- {h.get('fecha', '?')}: {h.get('texto', '')}" for h in historial[-6:]
    ) or "(sin conversación previa registrada)"

    plantilla_txt = (
        f"Título de la plantilla elegida: {plantilla_titulo or '(sin título)'}\n"
        f"Texto de la plantilla (ángulo/tema a seguir, personalizar y NO copiar literal):\n{plantilla_texto}"
        if plantilla_texto
        else "(Dionar no eligió una plantilla específica — guiate solo por la categoría.)"
    )

    user_prompt = (
        f"Prospecto: {nombre}\n"
        f"Etapa actual del CRM: {etapa or 'sin etapa'}\n"
        f"Cómo lo conoció / fuente: {fuente or 'sin especificar'}\n"
        f"Categoría de mensaje pedida: {categoria}\n"
        f"{plantilla_txt}\n\n"
        f"Nota general: {nota or '—'}\n"
        f"Motivo si está marcado 'No interesado': {motivo or '—'}\n\n"
        f"Historial de conversación reciente (orden cronológico):\n{hist_txt}\n\n"
        f"Para esta redacción en particular: {random.choice(_OPENING_STYLES)}.\n\n"
        f"Escribí el mensaje de WhatsApp siguiendo el ángulo de la plantilla elegida, coherente con lo que ya se hablaron."
    )

    texto = await call_llm(DRAFT_SYSTEM, user_prompt, max_tokens=400, temperature=0.95)
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
    "Calificás contactos para la Lista de 100 de un agente de seguros de vida (HGI/IUL), a "
    "partir de una descripción libre en español.\n\n"
    "REGLA PRINCIPAL — SÉ CONSERVADOR: marcá true SOLO si el texto lo dice explícitamente o lo "
    "implica de forma muy clara y directa. Ante cualquier duda, dejalo en false. Es MUCHO peor "
    "marcar true algo que el texto no sostiene, que dejar una casilla en false por falta de "
    "información. En una nota corta típica, la MAYORÍA de las 16 afirmaciones van a quedar en "
    "false — eso es lo normal y lo esperado, no un error tuyo.\n\n"
    "IMPORTANTE — esto NO es un ejercicio de \"hacer quedar bien\" al prospecto ni de venderle algo "
    "a Dionar: es una herramienta de FILTRADO real. Si marcás cosas en true sin evidencia, Dionar "
    "pierde tiempo real contactando a alguien que en realidad no calificaba. Marcar en false algo "
    "que no se puede confirmar NO es un fallo tuyo ni un juicio negativo sobre la persona — es "
    "simplemente honestidad con la información disponible. No asumas un perfil positivo genérico "
    "solo porque el texto describe a alguien de forma cercana o simpática.\n\n"
    "Definiciones para evitar ambigüedad:\n"
    "- Edad +25: el texto da una edad explícita de 25 años o más.\n"
    "- Casado: está CASADO Y CONVIVE actualmente con su pareja. Si el texto dice separado, "
    "divorciado, o que ya no vive con su pareja, esto es FALSE aunque haya estado casado antes "
    "o tenga hijos con esa persona.\n"
    "- Hijos: se menciona al menos un hijo/a.\n"
    "- EAD y Social: el texto menciona explícitamente permiso de trabajo (EAD) o número de "
    "seguro social.\n"
    "- U.S Resident: el texto dice explícitamente que vive/reside en Estados Unidos o tiene "
    "status migratorio legal ahí.\n"
    "- Bank Account: el texto menciona explícitamente que tiene cuenta bancaria.\n"
    "- High Income: el texto menciona explícitamente un ingreso alto o una situación económica "
    "claramente próspera — no lo asumas solo porque 'se le dan bien los negocios'.\n"
    "- Business Mindset: el texto muestra que la persona piensa en términos de negocio/"
    "emprendimiento propio (ej. 'se le dan bien los negocios', 'quiere poner algo propio').\n"
    "- People Skills: el texto describe explícitamente que es sociable, buen vendedor, le gusta "
    "hablar con gente, etc. — no lo asumas por defecto.\n"
    "- Coachable: el texto muestra explícitamente que la persona es abierta a aprender o recibir "
    "consejo — no lo asumas por defecto.\n"
    "- Tech Savvy: el texto menciona explícitamente manejo de tecnología, redes o computadoras.\n"
    "- Actively Looking: el texto dice que está buscando activamente un ingreso extra, trabajo o "
    "cambio (ej. 'anda buscando hacer más dinero').\n"
    "- Dissatisfied: el texto muestra insatisfacción explícita con su situación actual (trabajo, "
    "dinero, etc.).\n"
    "- Open To New Streams: el texto muestra apertura explícita a nuevas fuentes de ingreso.\n"
    "- Investments: el texto menciona explícitamente que invierte o le interesa invertir.\n"
    "- MLM: el texto menciona explícitamente experiencia o interés en multinivel/network "
    "marketing.\n\n"
    "Ejemplo real para calibrar cuán conservador ser:\n"
    "Texto: 'mi primo tiene 26 años, 1 hijo de 7, separado de su esposa, vive con su papá. Me "
    "dice que anda buscando hacer más dinero, se le dan bien los negocios.'\n"
    "Respuesta correcta: Edad +25=true, Casado=false (está separado), Hijos=true, EAD y "
    "Social=false, U.S Resident=false, Bank Account=false, High Income=false, Business "
    "Mindset=true, People Skills=false, Coachable=false, Tech Savvy=false, Actively "
    "Looking=true, Dissatisfied=true, Open To New Streams=true, Investments=false, MLM=false.\n\n"
    "PASO OBLIGATORIO ANTES DE RESPONDER: escribí primero un análisis breve (máximo 8 líneas), "
    "recorriendo las 16 afirmaciones UNA POR UNA, y para cada una anotá 'sí, porque el texto dice "
    "...' o 'no, no hay evidencia' — esto te obliga a chequear cada afirmación contra el texto real "
    "en vez de asumir un perfil genérico de buen prospecto. Se conservador: si estás listando "
    "'sí' para más de la mitad de las 16, pará y revisá de nuevo — en una nota corta típica eso "
    "casi seguro está mal.\n\n"
    "Después de ese análisis, en una línea aparte, escribí ÚNICAMENTE el JSON final (sin backticks, "
    "sin texto adicional después), con exactamente esta forma (reemplazando \"true/false\" por "
    "valores booleanos reales):\n" + _SCHEMA_EXAMPLE
)


@router.post("/calificar-l100")
async def calificar_l100(payload: dict, x_ai_token: str | None = Header(default=None, alias="X-AI-Token")):
    _check_token(x_ai_token)
    nota = str(payload.get("nota", "")).strip()
    if not nota:
        raise HTTPException(status_code=422, detail="falta 'nota'")

    texto = await call_llm(CALIFICAR_SYSTEM, nota, max_tokens=900, temperature=0.2)
    # log temporal de diagnóstico: nos deja ver el análisis + JSON crudo del modelo en los logs de
    # Railway para diagnosticar la calibración (ver [[trading_module_ia_prospeccion_backend_2026-09-10]]
    # en la memoria del proyecto — sacarlo una vez que la calibración esté confirmada estable).
    log.info("calificar-l100 | nota=%r | respuesta cruda del modelo:\n%s", nota[:200], texto)
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
