from src.bugbot.core.risk import calculate_contracts

tests = [
    {"symbol": "MNQ", "entry": 21000, "stop": 20975},  # 25 puntos stop
    {"symbol": "MES", "entry": 5300,  "stop": 5287.5}, # 12.5 puntos stop
    {"symbol": "MGC", "entry": 2350,  "stop": 2335},   # 15 puntos stop
]

for t in tests:
    r = calculate_contracts(
        symbol=t["symbol"],
        account_size=50_000,
        entry=t["entry"],
        stop=t["stop"],
        side='LONG'
    )
    print(f"\n=== {r.symbol} ===")
    print(f"Contratos: {r.contracts}")
    print(f"Riesgo:    ${r.risk_dollars}")
    print(f"Stop pts:  {r.stop_points}")
    for tp in r.tp_levels:
        print(f"{tp.name} → {tp.price} | {tp.contracts} contratos | ${tp.profit_usd}")
    print(f"Viable: {r.viable}")