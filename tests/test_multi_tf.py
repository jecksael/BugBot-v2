# tests/test_multi_tf.py
from __future__ import annotations
from tests.factories import make_df_from_closes, add_emas
from bugbot.core.multi_tf import weekly_bias, trend_4h, ema_cross_1h, confirm_15m_align

FAST, SLOW = 21, 52

def test_weekly_bias_bull_or_neutral():
    dfw = add_emas(make_df_from_closes(range(100, 200), freq="1W"), FAST, SLOW)
    out = weekly_bias(dfw, band=0.05, tilt_ok=0.995, fast=FAST, slow=SLOW)
    assert out in ("bull", "neutral")

def test_weekly_bias_bear():
    dfw = add_emas(make_df_from_closes(range(200, 100, -1), freq="1W"), FAST, SLOW)
    out = weekly_bias(dfw, band=0.05, tilt_ok=0.995, fast=FAST, slow=SLOW)
    assert out == "bear"

def test_trend_4h_reports_chop_or_up():
    df4 = add_emas(make_df_from_closes([100]*60 + list(range(100, 160)), freq="4H"), FAST, SLOW)
    out = trend_4h(df4, fast=FAST, slow=SLOW)
    assert out in ("up", "chop")

def test_ema_cross_1h_none_when_few_data():
    df1 = add_emas(make_df_from_closes([100, 101, 100, 99], freq="1H"), FAST, SLOW)
    out = ema_cross_1h(df1, fast=FAST, slow=SLOW)
    assert out is None

def test_confirm_15m_align_respects_side_long():
    df15 = add_emas(make_df_from_closes(range(100, 140), freq="15min"), FAST, SLOW)
    out = confirm_15m_align(df15, fast=FAST, slow=SLOW, bars=3, side="LONG")
    assert out in ("LONG", None)
