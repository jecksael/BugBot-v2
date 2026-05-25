from __future__ import annotations

import pandas as pd
import pytest

from bugbot.core.strategy import ema_fractal_signal


def _make_df(data: dict[str, list[float]]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(next(iter(data.values()))), freq="1H", tz="UTC")
    df = pd.DataFrame(data, index=idx)
    return df


def test_ema_fractal_signal_long_includes_fractal_meta():
    df = _make_df(
        {
            "open": [100, 101, 102, 100, 101, 103, 105],
            "high": [101, 102, 103, 101, 103, 106, 108],
            "low": [99, 98, 97, 94, 96, 101, 103],
            "close": [100, 101, 100, 95, 100, 105, 107],
            "volume": [1] * 7,
            "ema21": [100, 100, 99.5, 99, 99.5, 100, 106],
            "ema52": [100, 100, 100.1, 100.5, 100.8, 101.2, 104],
        }
    )

    sig = ema_fractal_signal(df, 21, 52, lookback=5, require_fractal=True)

    assert sig is not None
    assert sig["side"] == "LONG"
    assert sig["fractals"]["type"] == "bullish"
    assert sig["fractals"]["bars_ago"] == 3
    assert sig["sl_hint"] == pytest.approx(94)
    assert sig["risk_pct"] == pytest.approx((107 - 94) / 107, rel=1e-4)


def test_ema_fractal_signal_short_detects_bearish_setup():
    df = _make_df(
        {
            "open": [110, 109, 108, 109, 107, 106, 104],
            "high": [111, 110, 109, 113, 108, 107, 105],
            "low": [109, 107, 106, 105, 104, 103, 101],
            "close": [110, 108, 107, 106, 105, 104, 102],
            "volume": [1] * 7,
            "ema21": [110, 109, 108, 107, 106, 106, 102],
            "ema52": [109, 108, 107, 107, 106, 105, 103],
        }
    )

    sig = ema_fractal_signal(df, 21, 52, lookback=5, require_fractal=True)

    assert sig is not None
    assert sig["side"] == "SHORT"
    assert sig["fractals"]["type"] == "bearish"
    assert sig["fractals"]["bars_ago"] == 3
    assert sig["sl_hint"] == pytest.approx(113)
    assert sig["risk_pct"] == pytest.approx((113 - 102) / 102, rel=1e-4)


def test_ema_fractal_signal_can_ignore_fractal_requirement():
    df = _make_df(
        {
            "open": [100, 101, 102, 100, 101, 103, 105],
            "high": [101, 102, 103, 101, 103, 106, 108],
            "low": [99, 98, 97, 94, 96, 101, 103],
            "close": [100, 101, 100, 95, 100, 105, 107],
            "volume": [1] * 7,
            "ema21": [100, 100, 99.5, 99, 99.5, 100, 106],
            "ema52": [100, 100, 100.1, 100.5, 100.8, 101.2, 104],
        }
    )

    blocked = ema_fractal_signal(df, 21, 52, lookback=2, require_fractal=True)
    assert blocked is None

    allowed = ema_fractal_signal(df, 21, 52, lookback=2, require_fractal=False)
    assert allowed is not None
    assert allowed["fractals"]["bars_ago"] == 3
