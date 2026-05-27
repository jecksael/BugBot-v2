from tvdatafeed import TvDatafeed, Interval

# Sin login primero para probar
tv = TvDatafeed()

# Probar MNQ
df = tv.get_hist(
    symbol="MNQ1!",
    exchange="CME_MINI",
    interval=Interval.in_5_minute,
    n_bars=200
)

print(df.tail())
print("Columnas:", df.columns.tolist())