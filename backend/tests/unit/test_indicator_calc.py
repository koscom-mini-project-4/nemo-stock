"""지표 계산 순수 함수 단위 테스트 (기대값 고정)."""

from __future__ import annotations

import pytest

from app.nodes.indicator import calc


def test_sma_series():
    s = calc.sma_series([1, 2, 3, 4, 5], 3)
    assert s[:2] == [None, None]
    assert s[2] == pytest.approx(2.0)
    assert s[3] == pytest.approx(3.0)
    assert s[4] == pytest.approx(4.0)


def test_ema_series_seed_is_sma():
    values = [1, 2, 3, 4, 5, 6]
    e = calc.ema_series(values, 3)
    assert e[0] is None and e[1] is None
    # 시드 = 첫 3개의 SMA = 2.0
    assert e[2] == pytest.approx(2.0)
    # 다음 = 4*0.5 + 2*0.5 = 3.0
    assert e[3] == pytest.approx(3.0)


def test_rsi_all_gains_is_100():
    closes = [float(i) for i in range(1, 20)]  # 계속 상승
    r = calc.rsi_series(closes, 14)
    assert r[-1] == pytest.approx(100.0)


def test_rsi_known_direction():
    # 상승 후 하락 → RSI가 50 밑으로
    closes = [10, 11, 12, 13, 14, 15, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7]
    r = calc.rsi_series(closes, 14)
    assert r[-1] is not None
    assert r[-1] < 50


def test_stddev_sample():
    assert calc.stddev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=1e-2)


def test_max_drawdown_pct():
    # 100 -> 120 -> 90 : 고점 120 대비 90 = -25%
    assert calc.max_drawdown_pct([100, 120, 90, 100]) == pytest.approx(25.0)


def test_macd_series_lengths_match_input():
    closes = [float(100 + i) for i in range(40)]
    macd_line, signal_line, hist = calc.macd_series(closes, fast=12, slow=26, signal=9)
    assert len(macd_line) == len(closes)
    assert len(signal_line) == len(closes)
    assert len(hist) == len(closes)
    assert macd_line[-1] is not None


def test_atr_series_positive():
    highs = [105.0] * 20
    lows = [95.0] * 20
    closes = [100.0] * 20
    a = calc.atr_series(highs, lows, closes, window=14)
    assert a[-1] is not None
    assert a[-1] > 0


def test_rolling_max():
    rm = calc.rolling_max([1, 3, 2, 5, 4], 3)
    assert rm == [None, None, 3, 5, 5]
