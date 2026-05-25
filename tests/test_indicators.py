from __future__ import annotations

import pandas as pd

from bugbot.core.indicators import detect_fractals


def test_detect_fractals_marks_high_and_low_patterns():
    df = pd.DataFrame(
        {
            "open": [10, 11, 12, 11, 12, 13, 12],
            "high": [11, 12, 15, 13, 12, 14, 13],
            "low": [9, 8, 9, 6, 7, 9, 8],
            "close": [10, 11, 13, 7, 11, 12, 11],
            "volume": 1.0,
        }
    )

    out = detect_fractals(df)

    assert out.loc[2, "fractal_bearish"] is True
    assert out.loc[3, "fractal_bullish"] is True
    assert out.loc[[0, 1, 4, 5, 6], "fractal_bearish"].sum() == 0
    assert out.loc[[0, 1, 2, 4, 5, 6], "fractal_bullish"].sum() == 0


def test_detect_fractals_handles_empty_dataframe():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = detect_fractals(empty)
    assert "fractal_bearish" in out
    assert "fractal_bullish" in out
    assert out.empty
