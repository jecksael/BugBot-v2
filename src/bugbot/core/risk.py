# src/bugbot/core/risk.py
"""
BugBot v2.0 — Risk Engine para futuros de índices (NQ / MES)
Prop Firm: Apex Trader Funding
"""
from __future__ import annotations
from dataclasses import dataclass

# ─── Especificaciones de contratos CME ───────────────────────────────────────
CONTRACT_SPECS = {
    "NQ": {
        "tick_size":       0.25,   # mínimo movimiento
        "tick_value":      5.00,   # $ por tick
        "point_value":    20.00,   # $ por punto (4 ticks x $5)
    },
    "MES": {
        "tick_size":       0.25,
        "tick_value":      1.25,   # $ por tick
        "point_value":     5.00,   # $ por punto
    },
}

# ─── Reglas Apex por tamaño de cuenta ────────────────────────────────────────
APEX_RULES = {
    50_000: {
        "daily_loss_limit":    1_000,
        "trailing_drawdown":   2_500,
        "profit_target":       3_000,
        "max_contracts":       {"NQ": 3, "MES": 10},
        "default_stop_points": {"NQ": 15, "MES": 15},
        "default_risk_usd":    {"NQ": 300, "MES": 75},
    },
    100_000: {
        "daily_loss_limit":    2_000,
        "trailing_drawdown":   4_500,
        "profit_target":       6_000,
        "max_contracts":       {"NQ": 6, "MES": 15},
        "default_stop_points": {"NQ": 15, "MES": 15},
        "default_risk_usd":    {"NQ": 300, "MES": 75},
    },
}

# ─── Dataclasses de resultado ─────────────────────────────────────────────────
@dataclass
class RiskResult:
    symbol:           str
    account_size:     float
    risk_dollars:     float
    stop_points:      float
    contracts:        int
    point_value:      float
    daily_loss_limit: float
    max_contracts:    int
    risk_pct:         float
    viable:           bool
    reason:           str = ""

# ─── Función principal ────────────────────────────────────────────────────────
def calculate_contracts(
    symbol:       str,
    account_size: float,
    entry:        float,
    stop:         float,
    risk_pct:     float = 0.01,   # 1% por defecto
) -> RiskResult:
    """
    Calcula cuántos contratos operar dados:
    - symbol:       'NQ' o 'MES'
    - account_size: 50_000 o 100_000
    - entry:        precio de entrada
    - stop:         precio de stop loss
    - risk_pct:     % del capital a arriesgar (default 1%)
    """
    sym = symbol.upper()
    if sym not in CONTRACT_SPECS:
        raise ValueError(f"Símbolo no soportado: {sym}. Usa 'NQ' o 'MES'.")

    spec  = CONTRACT_SPECS[sym]
    rules = APEX_RULES.get(account_size)
    if rules is None:
        raise ValueError(f"Cuenta no soportada: ${account_size:,}. Usa 50000 o 100000.")

    # Dólares a arriesgar
    risk_dollars = account_size * risk_pct

    # Puntos de stop
    stop_points = abs(entry - stop)
    if stop_points < spec["tick_size"]:
        return RiskResult(
            symbol=sym, account_size=account_size,
            risk_dollars=risk_dollars, stop_points=stop_points,
            contracts=0, point_value=spec["point_value"],
            daily_loss_limit=rules["daily_loss_limit"],
            max_contracts=rules["max_contracts"][sym],
            risk_pct=risk_pct, viable=False,
            reason="Stop demasiado pequeño (menor a 1 tick)",
        )

    # Costo del stop por contrato
    stop_cost = stop_points * spec["point_value"]

    # Contratos óptimos
    raw = risk_dollars / stop_cost
    contracts = max(1, int(raw))

    # Aplicar límite Apex
    max_c = rules["max_contracts"][sym]
    if contracts > max_c:
        contracts = max_c

    # Verificar que el riesgo real no supere el daily loss limit
    real_risk = contracts * stop_cost
    viable = real_risk <= rules["daily_loss_limit"]
    reason = "" if viable else (
        f"Riesgo real ${real_risk:,.0f} supera daily loss limit "
        f"${rules['daily_loss_limit']:,}"
    )

    return RiskResult(
        symbol=sym,
        account_size=account_size,
        risk_dollars=risk_dollars,
        stop_points=stop_points,
        contracts=contracts,
        point_value=spec["point_value"],
        daily_loss_limit=rules["daily_loss_limit"],
        max_contracts=max_c,
        risk_pct=risk_pct,
        viable=viable,
        reason=reason,
    )


def make_targets(
    side:    str,
    entry:   float,
    sl:      float,
    steps:   tuple = (1, 2, 3),
) -> tuple[float, list[float], float]:
    """
    Genera TPs basados en el R (distancia entry→SL).
    Retorna: (sl, [tp1, tp2, tp3], R_en_puntos)
    """
    R = abs(entry - sl)
    if side.lower() == "long":
        tps = [entry + m * R for m in steps]
    else:
        tps = [entry - m * R for m in steps]
    return sl, tps, R