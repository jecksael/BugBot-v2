# tests/test_rules_engine.py
from __future__ import annotations
from .factories import make_df_from_closes, add_emas
from bugbot.core.rules_engine import eval_long_rule

FAST, SLOW = 21, 52

CFG = {
    "rules": {
        "threshold": 80,
        "long": [
            {"check": "weekly_bias",      "params": {"band": 0.05, "tilt_ok": 0.995, "fast": FAST, "slow": SLOW}, "weight": 30},
            {"check": "trend_4h",         "params": {"fast": FAST, "slow": SLOW}, "weight": 25},
            {"check": "ema_cross_1h",     "params": {"fast": FAST, "slow": SLOW}, "weight": 25},
            {"check": "ema_fractal_1h",   "params": {"fast": FAST, "slow": SLOW, "lookback": 5}, "weight": 15},
            {"check": "confirm_15m_align","params": {"fast": FAST, "slow": SLOW, "bars": 3}, "weight": 20},
        ]
    }
}

def bullish_data():
    dfw  = add_emas(make_df_from_closes(range(100, 130), freq="1W"), FAST, SLOW)
    df4  = add_emas(make_df_from_closes(range(100, 170), freq="4H"), FAST, SLOW)
    closes_1h = [100]*60 + [105, 103, 100, 98, 102, 107, 110]
    df1  = add_emas(make_df_from_closes(closes_1h, freq="1H"), FAST, SLOW)
    idx_prev, idx_last = df1.index[-2], df1.index[-1]
    df1.at[idx_prev, f"ema{FAST}"] = df1.at[idx_prev, "close"] * 0.98
    df1.at[idx_prev, f"ema{SLOW}"] = df1.at[idx_prev, "close"] * 1.00
    df1.at[idx_last, f"ema{FAST}"] = df1.at[idx_last, "close"] * 1.01
    df1.at[idx_last, f"ema{SLOW}"] = df1.at[idx_last, "close"] * 0.99
    df15 = add_emas(make_df_from_closes(range(100, 140), freq="15min"), FAST, SLOW)
    return {"1W": dfw, "4H": df4, "1H": df1, "15M": df15}

def test_eval_long_rule_scores_over_55_with_bullish_data():
    data = bullish_data()
    res = eval_long_rule(data, CFG)
    assert res.score >= 70  # weekly_bias (30) + trend_4h (25) + ema_fractal_1h (15)
    assert isinstance(res.reasons, list)
