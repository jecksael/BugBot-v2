from __future__ import annotations

from bugbot.core import metrics


def test_bump_signal_increments_counter_per_symbol():
    metrics.signals_emitted.clear()

    metrics.bump_signal("BTC/USDT")
    metrics.bump_signal("BTC/USDT")
    metrics.bump_signal("ETH/USDT")

    assert metrics.signals_emitted["BTC/USDT"] == 2
    assert metrics.signals_emitted["ETH/USDT"] == 1


def test_bump_reason_increments_counter_per_reason():
    metrics.reasons_blocked.clear()

    metrics.bump_reason("atr_filter=false")
    metrics.bump_reason("atr_filter=false")
    metrics.bump_reason("ema_cross_1h=no_signal")

    assert metrics.reasons_blocked["atr_filter=false"] == 2
    assert metrics.reasons_blocked["ema_cross_1h=no_signal"] == 1


def test_snapshot_returns_most_common_signals_and_blocks():
    metrics.signals_emitted.clear()
    metrics.reasons_blocked.clear()

    metrics.bump_signal("BTC/USDT")
    metrics.bump_signal("BTC/USDT")
    metrics.bump_signal("ETH/USDT")
    metrics.bump_reason("atr_filter=false")

    snap = metrics.snapshot(topn=1)

    assert snap["signals"] == [("BTC/USDT", 2)]
    assert snap["blocks"] == [("atr_filter=false", 1)]
