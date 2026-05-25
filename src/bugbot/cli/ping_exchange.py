from __future__ import annotations
from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..adapters.exchange import ExchangeClient
from ..core.indicators import add_ema

def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    ex = ExchangeClient.from_env()
    try:
        ex_id, df = ex.fetch_ohlcv_df("BTC/USDT", timeframe="1H", limit=200)
        df = add_ema(df, 21); df = add_ema(df, 52)
        last = df.iloc[-1]
        print(
            f"[{ex_id}] {last['date']}  "
            f"close={last['close']:.2f}  "
            f"ema21={last['ema21']:.2f}  "
            f"ema52={last['ema52']:.2f}"
        )
    finally:
        ex.close()

if __name__ == "__main__":
    main()
