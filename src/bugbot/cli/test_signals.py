from __future__ import annotations
import argparse
from typing import List, Tuple

from ..config.settings import get_settings
from ..config.logging import setup_logging
from ..adapters.exchange import ExchangeRouter

from ..core.indicators import add_ema, add_indicators_15m, add_indicators_4h
from ..strategies.advanced import find_signals_sniper_15m, find_signals_gato_15m


def _fmt(x: float) -> str:
    s = f"{x:,.2f}"
    return s.rstrip("0").rstrip(".")


def _print_signal(s) -> None:
    print(f"[{s.exchange}] {s.symbol} | {s.rule} {s.side} ✅ score={s.score}")
    print(
        "  "
        + f"entry={_fmt(s.entry)}  sl={_fmt(s.sl)}  "
        + f"tp={', '.join(_fmt(x) for x in s.tp)}  R={_fmt(s.R)}"
    )
    if s.reasons:
        print(f"  reasons: {', '.join(s.reasons)}")


def _prep(router: ExchangeRouter, symbol: str, limit15: int, limit4h: int, tf4h: str) -> Tuple[str, "pd.DataFrame", "pd.DataFrame"]:
    ex_id, df15 = router.fetch_ohlcv_df(symbol, timeframe="15m", limit=limit15)
    _,    df4h  = router.fetch_ohlcv_df(symbol, timeframe=tf4h,  limit=limit4h)

    # EMAs base
    for p in (21, 52, 100):
        df15 = add_ema(df15, p)
        df4h = add_ema(df4h, p)

    df15 = add_indicators_15m(df15)
    df4h = add_indicators_4h(df4h)
    return ex_id, df15, df4h


def scan_history(router: ExchangeRouter, symbol: str, max_signals: int, warmup: int, tf4h: str):
    """
    Recorre el histórico de 15m y, para cada barra, evalúa las reglas con los
    datos 'hasta ese momento'. Imprime las primeras `max_signals` señales.
    """
    ex_id, df15, df4h = _prep(router, symbol, limit15=800, limit4h=300, tf4h=tf4h)

    found = 0
    # empezamos después del warmup para que haya suficientes indicadores
    for i in range(max(warmup, 60), len(df15)):
        cur15 = df15.iloc[: i + 1]
        t     = cur15.index[-1]
        cur4h = df4h[df4h.index <= t]
        if len(cur4h) < 2:
            continue

        sigs = []
        sigs += find_signals_sniper_15m(ex_id, symbol, cur15, cur4h)
        sigs += find_signals_gato_15m(ex_id, symbol, cur15, cur4h)

        if sigs:
            for s in sigs:
                _print_signal(s)
                found += 1
                if found >= max_signals:
                    return

    if found == 0:
        print(f"[{ex_id}] {symbol}: no se encontraron señales en el rango analizado.")


def main():
    parser = argparse.ArgumentParser(description="BUGBot - test rápido de señales (histórico 15m)")
    parser.add_argument("--symbol", default=None, help="Símbolo a probar (ej: BTC/USDT). Si no se pasa, usa el primero de settings.")
    parser.add_argument("--max", type=int, default=5, help="Máximo de señales a imprimir.")
    parser.add_argument("--warmup", type=int, default=120, help="Barras de calentamiento para indicadores.")
    parser.add_argument("--tf4h", default="4H", help='Timeframe 4H (usa "4h" si tu adapter lo requiere).')
    args = parser.parse_args()

    s = get_settings()
    setup_logging(s.log_level)

    router = ExchangeRouter.from_env()
    symbol = args.symbol or (s.symbols[0] if s.symbols else "BTC/USDT")

    print(f"\n=== BUGBot test_signals ===")
    print(f"Symbol: {symbol} | max={args.max} | warmup={args.warmup} | tf4h={args.tf4h}\n")
    scan_history(router, symbol, max_signals=args.max, warmup=args.warmup, tf4h=args.tf4h)
    print("\nFin.\n")


if __name__ == "__main__":
    main()
