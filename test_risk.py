from src.bugbot.adapters.data import fetch_ohlcv
from src.bugbot.core.risk import calculate_contracts_dynamic, calc_atr

for sym in ["MNQ", "MES", "MGC"]:
    df = fetch_ohlcv(sym, "5m")
    atr = calc_atr(df)
    print(f"\n=== {sym} ===")
    print(f"ATR actual: {atr} puntos")

    r = calculate_contracts_dynamic(
        symbol=sym,
        account_size=50_000,
        entry=float(df["close"].iloc[-1]),
        side="LONG",
        df=df,
    )
    print(f"Contratos:  {r.contracts}")
    print(f"SL:         {r.stop} ({r.stop_points} pts)")
    print(f"Riesgo:     ${r.risk_dollars}")
    for tp in r.tp_levels:
        print(f"{tp.name} → {tp.price} | {tp.contracts} contratos | ${tp.profit_usd}")
    print(f"Viable: {r.viable}")