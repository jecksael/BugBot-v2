from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict
import yaml
import pandas as pd

# === IMPORTS TUS CHECKS EXISTENTES ===
from .multi_tf import weekly_bias, trend_4h, ema_cross_1h, confirm_15m_align
from .strategy import ema_fractal_signal

# Si tus indicadores ya agregan ema21/ema52/atr14/vol_sma20/atr_pct/gap_2152_pct, perfecto.
# En caso contrario, asegúrate de calcularlos en add_indicators_* antes de llamar al evaluator.

# ---------------------------------------------------------------------------
# Tipos y registro
# ---------------------------------------------------------------------------
CheckFn = Callable[..., Any]

@dataclass
class EvalResult:
    passed: bool
    score: int
    reasons: list[str]

# ---------------------------------------------------------------------------
# Checks NUEVOS (filtros/confirmaciones)
#   Esperan un DataFrame ya con indicadores; usan la última fila.
# ---------------------------------------------------------------------------

def atr_filter(df: pd.DataFrame, *, min_pct: float, max_pct: float, **_) -> bool:
    """ATR% dentro de rango [min_pct, max_pct]."""
    row = df.iloc[-1]
    atr_pct = float(row.get("atr_pct", 0.0))
    return (atr_pct >= min_pct) and (atr_pct <= max_pct)

def near_cross_gap(df: pd.DataFrame, *, max_gap_pct: float, **_) -> bool:
    """Gap EMA21/52 pequeño: “casi cruce”."""
    row = df.iloc[-1]
    gap = float(row.get("gap_2152_pct", 999.0))
    return gap <= max_gap_pct

def volume_boost(df: pd.DataFrame, *, sma_period: int = 20, **_) -> bool:
    """Volumen actual > SMA(period) de volumen."""
    row = df.iloc[-1]
    vol = float(row.get("volume", 0.0))
    vol_sma = float(row.get(f"vol_sma{sma_period}", row.get("vol_sma20", 0.0)))
    # si no hay volumen (algunos cripto feeds), falla silencioso:
    if vol_sma == 0:
        return False
    return vol > vol_sma

def htf_bias(df_htf: pd.DataFrame, *, fast: int = 21, slow: int = 52, tf: str = "4h", side: str = "long", **_) -> bool:
    """
    Alineación con HTF: EMA21 vs EMA52 en HTF.
    - Para long: EMA21 > EMA52
    - Para short: EMA21 < EMA52
    """
    row = df_htf.iloc[-1]
    ema21 = float(row.get("ema21", row.get(f"ema{fast}", 0.0)))
    ema52 = float(row.get("ema52", row.get(f"ema{slow}", 0.0)))
    if side == "long":
        return ema21 > ema52
    else:
        return ema21 < ema52

# ---------------------------------------------------------------------------
# Registro de todos los checks
# (mantenemos tus existentes y añadimos los nuevos)
# ---------------------------------------------------------------------------
CHECKS: dict[str, CheckFn] = {
    # existentes
    "weekly_bias": weekly_bias,
    "trend_4h": trend_4h,
    "ema_cross_1h": ema_cross_1h,
    "confirm_15m_align": confirm_15m_align,
    "ema_fractal_1h": ema_fractal_signal,
    # nuevos
    "atr_filter": atr_filter,
    "near_cross_gap": near_cross_gap,
    "volume_boost": volume_boost,
    "htf_bias": htf_bias,
}

# ---------------------------------------------------------------------------
# Utilidad: carga YAML
# ---------------------------------------------------------------------------
def load_rules(path: str | None = None) -> dict:
    default = Path(__file__).resolve().parents[1] / "config" / "rules.yaml"
    p = Path(path) if path else default
    if not p.exists():
        p = default
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Evaluador genérico: soporta long y short
# data: {'1W': dfw, '4H': df4, '1H': df1, '15M': df15}
# side: 'long' | 'short'
# ---------------------------------------------------------------------------
def eval_rules(data: Dict[str, pd.DataFrame], cfg: dict, side: str) -> EvalResult:
    rules = cfg["rules"][side]
    threshold = int(cfg["rules"].get("threshold", 100))
    score, reasons = 0, []

    for item in rules:
        name = item.get("check")
        if not name:
            continue
        fn = CHECKS[name]
        params = item.get("params", {}) or {}
        weight = int(item.get("weight", 0))

        # ---- checks con lógica específica (usan varios TF o comparan por lado) ----
        if name == "weekly_bias":
            out = fn(data["1W"], **params)  # tu fn devuelve 'bull'/'bear'/'neutral'
            if side == "long":
                ok = out in ("bull", "neutral")
            else:
                ok = out in ("bear", "neutral")
            if ok: score += weight
            else: reasons.append(f"{name}={out}")

        elif name == "trend_4h":
            out = fn(data["4H"], **params)  # tu fn devuelve 'up'/'down'/'flat'
            ok = (out == "up") if side == "long" else (out == "down")
            if ok: score += weight
            else: reasons.append(f"{name}={out}")

        elif name == "ema_cross_1h":
            out = fn(data["1H"], **params)  # 'LONG'/'SHORT'/None
            ok = (out == "LONG") if side == "long" else (out == "SHORT")
            if ok: score += weight
            else: reasons.append(f"{name}={out or 'no_signal'}")

        elif name == "confirm_15m_align":
            # Confirmación en 15m alineada con el lado real
            side_from_1h = ema_cross_1h(data["1H"], params.get("fast", 21), params.get("slow", 52))
            out = CHECKS["confirm_15m_align"](data["15M"], **params, side=side_from_1h)
            ok = (out == "LONG") if side == "long" else (out == "SHORT")
            if ok: score += weight
            else: reasons.append(f"{name}={out or 'no_signal'}")

        elif name == "ema_fractal_1h":
            sig = fn(
                data["1H"],
                params.get("fast", 21),
                params.get("slow", 52),
                lookback=params.get("lookback", 5),
                require_fractal=params.get("require_fractal", True),
            )
            out = (sig or {}).get("side")
            ok = (out == "LONG") if side == "long" else (out == "SHORT")
            if ok: score += weight
            else: reasons.append(f"{name}={out or 'no_signal'}")

        # ---- checks nuevos: usan DF del TF indicado y son booleanos ----
        elif name in ("atr_filter", "near_cross_gap", "volume_boost"):
            # Estos se evalúan normalmente en 1H (coherente con cruce); si prefieres otro TF, cámbialo.
            ok = fn(data["1H"], **params)
            if ok: score += weight
            else: reasons.append(f"{name}=false")

        elif name == "htf_bias":
            # explícitamente en 4H por default (params.tf), pero usamos data['4H']
            ok = fn(data["4H"], **params, side=side)
            if ok: score += weight
            else: reasons.append(f"{name}=misaligned")

        else:
            # fallback: si agregas nuevos checks personalizados
            try:
                ok = bool(fn(data["1H"], **params))
                if ok: score += weight
                else: reasons.append(f"{name}=false")
            except Exception as e:
                reasons.append(f"{name}=error:{e!r}")

    return EvalResult(passed=(score >= threshold), score=score, reasons=reasons)

# Azúcar sintáctico para mantener compatibilidad con tu código actual
def eval_long_rule(data: Dict[str, pd.DataFrame], cfg: dict) -> EvalResult:
    return eval_rules(data, cfg, side="long")

def eval_short_rule(data: Dict[str, pd.DataFrame], cfg: dict) -> EvalResult:
    return eval_rules(data, cfg, side="short")
