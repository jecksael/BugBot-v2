# src/bugbot/core/risk.py
"""
BugBot v2.0 — Risk Engine para futuros de índices (NQ / MES / MGC)
Prop Firm: Apex Trader Funding
R:R 1:4 con salida escalonada 50/30/20 + BE después de TP1
"""
from __future__ import annotations
from dataclasses import dataclass, field

# ─── Especificaciones de contratos CME ───────────────────────────────────────
CONTRACT_SPECS = {
    "NQ": {
        "tick_size":    0.25,
        "tick_value":   5.00,
        "point_value": 20.00,
        "default_risk": 250,
    },
    "MNQ": {
        "tick_size":    0.25,
        "tick_value":   0.50,
        "point_value":  2.00,
        "default_risk": 250,
    },
    "MES": {
        "tick_size":    0.25,
        "tick_value":   1.25,
        "point_value":  5.00,
        "default_risk":  30,
    },
    "MGC": {
        "tick_size":    0.10,
        "tick_value":   1.00,
        "point_value": 10.00,
        "default_risk": 150,
    },
}

# ─── Reglas Apex por tamaño de cuenta ────────────────────────────────────────
APEX_RULES = {
    50_000: {
        "daily_loss_limit":    1_000,
        "trailing_drawdown":   2_500,
        "profit_target":       3_000,
        "max_contracts": {"NQ": 3, "MES": 10, "MGC": 5, "MNQ": 10},
        "default_stop_points": {"NQ": 12.5, "MES": 6, "MGC": 15, "MNQ": 12.5},
    },
    100_000: {
        "daily_loss_limit":    2_000,
        "trailing_drawdown":   4_500,
        "profit_target":       6_000,
        "max_contracts": {"NQ": 6, "MES": 15, "MGC": 10,"MNQ": 15},
        "default_stop_points": {"NQ": 12.5, "MES": 6, "MGC": 15, "MNQ": 12.5},
    },
}

# ─── Distribución de salidas ──────────────────────────────────────────────────
EXIT_DISTRIBUTION = {
    "TP1": {"r_multiple": 1, "pct_exit": 0.50},  # 50% en 1R
    "TP2": {"r_multiple": 2, "pct_exit": 0.30},  # 30% en 2R
    "TP3": {"r_multiple": 4, "pct_exit": 0.20},  # 20% en 4R (runner)
}

# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class TPLevel:
    name:       str
    price:      float
    r_multiple: float
    pct_exit:   float
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
    sym = symbol.upper()
    if sym not in CONTRACT_SPECS:
        raise ValueError(f"Símbolo no soportado: {sym}. Usa NQ, MES o MGC.")

    spec  = CONTRACT_SPECS[sym]
    rules = APEX_RULES.get(account_size)
    if rules is None:
        raise ValueError(f"Cuenta no soportada: ${account_size:,}. Usa 50000 o 100000.")

    risk_dollars = spec["default_risk"]
    stop_points  = abs(entry - stop)

    if stop_points < spec["tick_size"]:
        return RiskResult(
            symbol=sym, account_size=account_size, side=side,
            entry=entry, stop=stop, stop_points=stop_points,
            contracts=0, risk_dollars=risk_dollars,
            point_value=spec["point_value"],
            daily_loss_limit=rules["daily_loss_limit"],
            max_contracts=rules["max_contracts"][sym],
            viable=False, reason="Stop menor a 1 tick",
        )

    # Contratos óptimos
    stop_cost = stop_points * spec["point_value"]
    contracts = max(1, int(risk_dollars / stop_cost))
    contracts = min(contracts, rules["max_contracts"][sym])

    # Riesgo real
    real_risk = contracts * stop_cost
    viable    = real_risk <= rules["daily_loss_limit"]

    # Calcular TPs con distribución 50/30/20
    R   = stop_points
    tps = []
    for name, cfg in EXIT_DISTRIBUTION.items():
        mult  = cfg["r_multiple"]
        pct   = cfg["pct_exit"]
        if side.upper() == "LONG":
            price = entry + (R * mult)
        else:
            price = entry - (R * mult)
        profit = contracts * pct * R * mult * spec["point_value"]
        tps.append(TPLevel(
            name=name, price=round(price, 2),
            r_multiple=mult, pct_exit=pct,
            profit_usd=round(profit, 2),
        ))

    return RiskResult(
        symbol=sym, account_size=account_size, side=side,
        entry=entry, stop=stop, stop_points=stop_points,
        contracts=contracts, risk_dollars=real_risk,
        point_value=spec["point_value"],
        daily_loss_limit=rules["daily_loss_limit"],
        max_contracts=rules["max_contracts"][sym],
        tp_levels=tps, breakeven_after="TP1",
        viable=viable,
        reason="" if viable else f"Riesgo ${real_risk:,.0f} supera daily limit ${rules['daily_loss_limit']:,}",
    )


def make_targets(
    side:  str,
    entry: float,
    sl:    float,
) -> tuple[float, list[float], float]:
    R   = abs(entry - sl)
    mults = [cfg["r_multiple"] for cfg in EXIT_DISTRIBUTION.values()]
    if side.lower() == "long":
        tps = [entry + m * R for m in mults]
    else:
        tps = [entry - m * R for m in mults]
    return sl, tps, R