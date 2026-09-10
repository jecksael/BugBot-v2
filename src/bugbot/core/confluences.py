# src/bugbot/core/confluences.py
"""
BugBot v2.0 — Confluencias de precisión (Order Block + FVG)

Detección propia sobre el DataFrame OHLCV que ya usa strategy_smc.py, con
definiciones estándar de SMC/ICT (no derivadas del código de ningún indicador
de terceros). Puramente aditivo: nunca decide side/entry/sl — detect_signal()
sigue siendo la única fuente de verdad para eso. Esto solo añade etiquetas
para que el journal (BugBot y, después, journal.html) sepa POR QUÉ se disparó
cada señal, sin que nadie tenga que interpretar una captura de pantalla.

Definiciones usadas:
  - FVG (Fair Value Gap): patrón de 3 velas consecutivas donde la vela 1 y la
    vela 3 no solapan su rango — deja un "hueco" de precio sin operar.
      Alcista: low(vela3)  > high(vela1)  -> zona = (high(vela1), low(vela3))
      Bajista: high(vela3) < low(vela1)   -> zona = (high(vela3), low(vela1))
  - Order Block: la última vela de color contrario al impulso, justo antes
    de un tramo de al menos 2 velas en la dirección del setup.
      Alcista: última vela bajista antes de un tramo alcista -> zona = su rango.
      Bajista: última vela alcista antes de un tramo bajista -> zona = su rango.

Ambas se consideran válidas solo si siguen "sin mitigar" (el precio no cerró
ya en contra de la zona desde que se formó) al momento de la vela de
confirmación actual.
"""
from __future__ import annotations
import pandas as pd

from . import state as _state


def _is_unmitigated(df: pd.DataFrame, zone_low: float, zone_high: float, since_idx: int, side: str) -> bool:
    """
    True si, desde que se formó la zona (since_idx, inclusive) hasta la vela
    ANTERIOR a la actual, el precio no cerró ya en contra de la zona.
    """
    n = len(df)
    if since_idx >= n - 1:
        return True  # se formó en la vela de confirmación misma: nada que invalidarla aún
    closes = df["close"].iloc[since_idx:n - 1]
    if side == "LONG":
        return not (closes < zone_low).any()
    else:
        return not (closes > zone_high).any()


def detect_fvg(df: pd.DataFrame, side: str, lookback: int = 15) -> bool:
    """
    Busca, entre las últimas `lookback` velas (incluida la de confirmación
    como posible vela 3), un FVG en la dirección del setup que siga sin
    rellenar. Empieza por el más reciente.
    """
    n = len(df)
    if n < 3:
        return False
    start_k = max(2, n - lookback)
    for k in range(n - 1, start_k - 1, -1):
        c1 = df.iloc[k - 2]
        c3 = df.iloc[k]
        if side == "LONG" and c3["low"] > c1["high"]:
            if _is_unmitigated(df, float(c1["high"]), float(c3["low"]), k, side):
                return True
        elif side == "SHORT" and c3["high"] < c1["low"]:
            if _is_unmitigated(df, float(c3["high"]), float(c1["low"]), k, side):
                return True
    return False


def detect_order_block(df: pd.DataFrame, side: str, lookback: int = 15, min_follow: int = 2) -> bool:
    """
    Busca la última vela de color contrario al setup, seguida de al menos
    `min_follow` velas del color del setup hasta la vela de confirmación
    (excluida), y que esa zona siga sin mitigar.
    """
    n = len(df)
    confirm_idx = n - 1
    if confirm_idx < min_follow + 1:
        return False
    start = max(0, confirm_idx - lookback)

    for i in range(confirm_idx - 1, start - 1, -1):
        row = df.iloc[i]
        follow = df.iloc[i + 1:confirm_idx]
        if len(follow) < min_follow:
            continue
        if side == "LONG" and row["close"] < row["open"]:
            if (follow["close"] > follow["open"]).sum() >= min_follow:
                zone_low, zone_high = float(row["low"]), float(row["high"])
                return _is_unmitigated(df, zone_low, zone_high, i + 1, side)
        elif side == "SHORT" and row["close"] > row["open"]:
            if (follow["close"] < follow["open"]).sum() >= min_follow:
                zone_low, zone_high = float(row["low"]), float(row["high"])
                return _is_unmitigated(df, zone_low, zone_high, i + 1, side)
    return False


def compute_confluences(df: pd.DataFrame, sig: dict, symbol: str, timeframe: str) -> list[str]:
    """
    Devuelve la lista de etiquetas de confluencia para una señal YA
    confirmada (sig['ok'] is True), usando los mismos nombres que ya
    reconoce journal.html (data-conf="...") para que encajen directo en
    el campo `confs` sin traducción manual.

    Nunca lanza — cualquier excepción interna se deja subir para que quien
    llame decida (se recomienda envolver esta llamada en try/except y
    seguir sin confluencias si algo falla, para no bloquear la señal real).
    """
    side = sig["side"]
    bias = sig["bias"]
    event = sig.get("event") or sig.get("zona") or ""

    tags: list[str] = []

    structure_event = _state.classify_and_update(symbol, bias)
    if structure_event == "CHoCH":
        tags.append(f"CHoCH {_state.tf_label(timeframe)}")
    elif event.upper() == "BOS":
        tags.append("BOS alcista" if side == "LONG" else "BOS bajista")
    elif event.upper() == "SWEEP":
        tags.append("Barrido de liquidez")

    if detect_order_block(df, side):
        tags.append("Order Block")
    if detect_fvg(df, side):
        tags.append("FVG")

    return tags


def label_structure_from_zona(zona: str, side: str, timeframe: str) -> str | None:
    """
    Para señales que llegan por webhook.py: a diferencia del poller (donde
    Python calcula la estructura desde cero), acá la estructura YA viene
    clasificada por el indicador de TradingView en el texto `zona` que vos
    mismo escribiste en el mensaje de la alerta (ej. "Internal BOS"). Esta
    función solo traduce ese texto al mismo vocabulario de journal.html —
    no recalcula nada ni asume nada que la alerta no diga.
    """
    z = (zona or "").upper()
    if "CHOCH" in z:
        return f"CHoCH {_state.tf_label(timeframe)}"
    if "BOS" in z:
        return "BOS alcista" if side == "LONG" else "BOS bajista"
    if "SWEEP" in z or "BARRIDO" in z:
        return "Barrido de liquidez"
    return None


def compute_confluences_webhook(zona: str, side: str, df, timeframe: str) -> list[str]:
    """
    Equivalente a compute_confluences() pero para el pipeline real (alertas
    de TradingView vía webhook.py, no el poller). La estructura sale del
    texto `zona` de la alerta; Order Block y FVG se calculan en Python sobre
    las velas ya bajadas para el ATR — si `df` es None (por ejemplo, RTS sin
    velas disponibles), esas dos quedan simplemente sin marcar.
    """
    tags: list[str] = []

    label = label_structure_from_zona(zona, side, timeframe)
    if label:
        tags.append(label)

    if df is not None and len(df) >= 5:
        if detect_order_block(df, side):
            tags.append("Order Block")
        if detect_fvg(df, side):
            tags.append("FVG")

    return tags
