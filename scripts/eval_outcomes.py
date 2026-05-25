def first_touch(side, entry, sl, tps, future_df):
    # future_df: velas posteriores (high/low) desde la vela después de la señal
    for _, r in future_df.iterrows():
        hi, lo = float(r["high"]), float(r["low"])
        if side=="LONG":
            if lo <= sl: return ("SL",  -1.0)
            for i, tp in enumerate(tps, start=1):
                if hi >= tp: return (f"TP{i}",  float(i))  # i R
        else:
            if hi >= sl: return ("SL",  -1.0)
            for i, tp in enumerate(tps, start=1):
                if lo <= tp: return (f"TP{i}",  float(i))
    return ("OPEN", 0.0)
