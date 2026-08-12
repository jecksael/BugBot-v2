# src/bugbot/core/risk.py
"""
BugBot v2.0 — Risk Engine para futuros de índices (MNQ / MES / MGC)
Prop Firm: Apex Trader Funding
"""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd
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
# ─── SL dinámico con ATR  ─────────────────────────────────────────────────────

def calc_atr(df, period: int = 14) -> float:
    """
    Calcula el ATR actual del DataFrame.
    """
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low  - close.shift()).abs()

    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return round(float(atr), 2)


def calc_dynamic_sl(
    symbol:     str,
    entry:      float,
    side:       str,
    atr:        float,
    multiplier: float = 1.5,
) -> tuple[float, float]:
    """
    Calcula SL dinámico basado en ATR.
    Retorna: (precio_sl, puntos_sl)
    """
    sym        = symbol.upper()
    stop_points = round(atr * multiplier, 2)

    if side.upper() == "LONG":
        sl = entry - stop_points
    else:
        sl = entry + stop_points

    return round(sl, 2), stop_points


def calculate_contracts_dynamic(
    symbol:       str,
    account_size: float,
    entry:        float,
    side:         str,
    df,
    atr_period:   int   = 14,
    atr_mult:     float = 1.5,
) -> RiskResult:
    """
    Calcula contratos con SL dinámico basado en ATR.
    Ajusta contratos automáticamente si el riesgo supera el límite.
    """
    import pandas as pd

    sym   = symbol.upper()
    spec  = CONTRACT_SPECS.get(sym)
    rules = APEX_RULES.get(account_size)

    if not spec:
        raise ValueError(f"Símbolo no soportado: {sym}")
    if not rules:
        raise ValueError(f"Cuenta no soportada: ${account_size:,}")

    # Calcular ATR y SL dinámico
    atr              = calc_atr(df, atr_period)
    sl, stop_points  = calc_dynamic_sl(sym, entry, side, atr, atr_mult)

    # Contratos base
    contracts    = spec["contracts"]
    max_c        = rules["max_contracts"][sym]
    daily_limit  = rules["daily_loss_limit"]
    max_risk     = daily_limit * 0.5  # máx 50% del daily limit por trade

    # Ajustar contratos si el riesgo es muy alto
    stop_cost = stop_points * spec["point_value"]
    while contracts > 1:
        real_risk = contracts * stop_cost
        if real_risk <= max_risk:
            break
        contracts -= 1

    real_risk = contracts * stop_cost
    viable    = real_risk <= daily_limit

    # Calcular TPs con el R dinámico
    R    = stop_points
    tps  = []
    plan = EXIT_PLANS.get(sym, [])

    # Ajustar contratos del plan si se redujeron
    total_plan = sum(t["contracts"] for t in plan)
    for tp in plan:
        c_ratio = tp["contracts"] / total_plan
        c       = max(1, round(contracts * c_ratio))
        mult    = tp["r_multiple"]
        price   = entry + (R * mult) if side.upper() == "LONG" else entry - (R * mult)
        profit  = c * R * mult * spec["point_value"]
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
        stop=sl,
        stop_points=stop_points,
        contracts=contracts,
        risk_dollars=round(real_risk, 2),
        point_value=spec["point_value"],
        daily_loss_limit=daily_limit,
        max_contracts=max_c,
        tp_levels=tps,
        breakeven_after="TP1",
        viable=viable,
        reason="" if viable else f"Riesgo ${real_risk:,.0f} supera daily limit",
    )
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
        {"name": "TP1", "r_multiple": 1, "contracts": 2},
        {"name": "TP2", "r_multiple": 2, "contracts": 1},
        {"name": "TP3", "r_multiple": 4, "contracts": 1},
    ],
    "MES": [
        {"name": "TP1", "r_multiple": 1, "contracts": 1},  # 1 contrato en 1R
        {"name": "TP3", "r_multiple": 4, "contracts": 1},  # 1 contrato en 4R
    ],
    "MGC": [
        {"name": "TP1", "r_multiple": 1, "contracts": 1},  # 1R
        {"name": "TP2", "r_multiple": 2, "contracts": 1},  # 2R
        {"name": "TP3", "r_multiple": 3, "contracts": 1},  # 3R
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
