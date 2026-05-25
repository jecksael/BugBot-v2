from src.bugbot.core.risk import calculate_contracts

r = calculate_contracts(
    symbol='NQ',
    account_size=50_000,
    entry=21000,
    stop=20987.5,
    side='LONG'
)
print(f'Contratos: {r.contracts}')
print(f'Riesgo: ${r.risk_dollars}')
print(f'Stop pts: {r.stop_points}')
for tp in r.tp_levels:
    print(f'{tp.name} -> {tp.price} | salida {int(tp.pct_exit*100)}% | ganancia ${tp.profit_usd}')
print(f'BE despues de: {r.breakeven_after}')