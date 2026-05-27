# src/bugbot/core/risk.py
"""
BugBot v2.0 — Risk Engine para futuros de índices (MNQ / MES / MGC)
Prop Firm: Apex Trader Funding
"""
from __future__ import annotations
from dataclasses import dataclass, field

# ─── Especificaciones de contratos CME ───────────────────────────────────────
CONTRACT_SPECS = {
    "MNQ": {
        "tick_size":    0.25,
        "tick_value":   0.50,
        "point_value":  2.00,
        "default_stop": 25,      # puntos
        "default_risk": 200,     # dólares (4 contratos x 25pts x $2)
        "contracts":    4,
    },
    "MES": {
        "tick_size":    0.25,
        "tick_value":   1.25,
        "point_value":  5.00,
        "default_stop": 12.5,
        "default_risk": 125,     # dólares (2 contratos x 12.5pts x $5)
        "contracts":    2,
    },
    "MGC": {
        "tick_size":    0.10,
        "tick_value":   1.00,
        "point_value":  10.00,
        "default_stop": 15,
        "default_risk": 150,     # dólares (1 contrato x 15pts x $10)
        "contracts":    1,
    },
}

# ─── Reglas Apex ─────────────────────────────────────────────────────────────
APEX_RULES = {
    50_000: {
        "daily_loss_limit":  1_000,
        "trailing_drawdown": 2_500,
        "profit_target":     3_000,
        "max_contracts": {"MNQ": 4, "MES": 2, "MGC": 1},
    },
    100_000: {
        "daily_loss_limit":  2_000,
        "trailing_drawdown": 4_500,
        "profit_target":     6_000,
        "max_contracts": {"MNQ": 8, "MES": 4, "MGC": 2},
    },
}

# ─── Distribución de salidas ──────────────────────────────────────────────────
EXIT_PLANS = {
    "MNQ": [
        {"name": "TP1", "r_multiple": 1, "contracts": 2},  # 2 contratos en 1R
        {"name": "TP3", "r_multiple": 4, "contracts": 2},  # 2 contratos en 4R
    ],
    "MES": [
        {"name": "TP1", "r_multiple": 1, "contracts": 1},  # 1 contrato en 1R
        {"name": "TP3", "r_multiple": 4, "contracts": 1},  # 1 contrato en 4R
    ],
    "MGC": [
        {"name": "TP2", "r_multiple": 2, "contracts": 1},  # 1 contrato en 2R
    ],
}

# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class TPLevel:
    name:       str
    price:      float
    r_multiple: float
    contracts:  int
    profit_usd: float

@dataclass
class RiskResult:
    symbol:           str
    account_size:     float
    side:             str
    entry:            float
    stop:             float
    stop_points:      float
    contracts:        int
    risk_dollars:     float
    point_value:      float
    daily_loss_limit: float
    max_contracts:    int
    tp_levels:        list[TPLevel] = field(default_factory=list)
    breakeven_after:  str  = "TP1"
    viable:           bool = True
    reason:           str  = ""

# ─── Función principal ────────────────────────────────────────────────────────
def calculate_contracts(
    symbol:       str,
    account_size: float,
    entry:        float,
    stop:         float,
    side:         str = "LONG",
) -> RiskResult:
    sym   = symbol.upper()
    spec  = CONTRACT_SPECS.get(sym)
    rules = APEX_RULES.get(account_size)

    if not spec:
        raise ValueError(f"Símbolo no soportado: {sym}. Usa MNQ, MES o MGC.")
    if not rules:
        raise ValueError(f"Cuenta no soportada: ${account_size:,}.")

    contracts    = spec["contracts"]
    stop_points  = abs(entry - stop)
    stop_cost    = stop_points * spec["point_value"] * contracts
    real_risk    = stop_cost
    viable       = real_risk <= rules["daily_loss_limit"]

    # Calcular TPs
    R    = stop_points
    tps  = []
    plan = EXIT_PLANS.get(sym, [])

    for tp in plan:
        mult  = tp["r_multiple"]
        c     = tp["contracts"]
        price = entry + (R * mult) if side.upper() == "LONG" else entry - (R * mult)
        profit = c * R * mult * spec["point_value"]
        tps.append(TPLevel(
            name=tp["name"],
            price=round(price, 2),
            r_multiple=mult,
            contracts=c,
            profit_usd=round(profit, 2),
        ))

    return RiskResult(
        symbol=sym,
        account_size=account_size,
        side=side,
        entry=entry,
        stop=stop,
        stop_points=stop_points,
        contracts=contracts,
        risk_dollars=round(real_risk, 2),
        point_value=spec["point_value"],
        daily_loss_limit=rules["daily_loss_limit"],
        max_contracts=rules["max_contracts"][sym],
        tp_levels=tps,
        breakeven_after="TP1",
        viable=viable,
        reason="" if viable else f"Riesgo ${real_risk:,.0f} supera daily limit",
    )

def make_targets(
    side:  str,
    entry: float,
    sl:    float,
) -> tuple[float, list[float], float]:
    R   = abs(entry - sl)
    if side.lower() == "long":
        tps = [entry + m * R for m in [1, 2, 4]]
    else:
        tps = [entry - m * R for m in [1, 2, 4]]
    return sl, tps, R