import yfinance as yf

# NQ Futures
nq = yf.download("NQ=F", period="5d", interval="5m")
print("=== NQ ===")
print(nq.tail())
print(nq.columns.tolist())