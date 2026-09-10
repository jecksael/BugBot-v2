# src/bugbot/core/state.py
"""
BugBot v2.0 — Estado mínimo persistente entre ciclos (JSON plano, sin DB).

Hoy solo guarda el bias de estructura del ciclo anterior por símbolo, para
poder distinguir un evento de CONTINUACIÓN (BOS) de un GIRO real de
estructura (CHoCH) sin tocar la lógica de detect_signal() en strategy_smc.py.
"""
from __future__ import annotations
import json
from pathlib import Path

STATE_PATH = Path("data/bot_state.json")

TF_LABELS = {"1m": "1M", "5m": "5M", "15m": "15M", "1h": "1H", "4h": "4H"}


def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state: dict) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def classify_and_update(symbol: str, bias: str) -> str:
    """
    Compara `bias` contra el último bias guardado para `symbol`.
    - Primera vez que se ve el símbolo -> "BOS" (no hay giro que detectar).
    - Bias igual al del ciclo anterior -> "BOS" (continuación).
    - Bias distinto -> "CHoCH" (giro de estructura).
    Actualiza el estado guardado en cualquier caso.
    """
    state = _load()
    prev_bias = state.get(symbol)
    event = "CHoCH" if (prev_bias is not None and prev_bias != bias) else "BOS"
    state[symbol] = bias
    _save(state)
    return event


def tf_label(timeframe: str) -> str:
    return TF_LABELS.get(timeframe, (timeframe or "").upper())
