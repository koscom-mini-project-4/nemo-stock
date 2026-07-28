"""Phase 2 확장 지표(감성 우위도/종목 점수/거시 심리/모멘텀 가속도/버즈/이벤트 밀도) 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.dao.base import NewsSignalRecord
from app.news_signals.aggregate import (
    buzz_zscore,
    event_density,
    macro_sentiment_index,
    momentum_change,
    sentiment_ratio,
    symbol_news_stats,
)

AS_OF = datetime(2026, 7, 19, 12, 0, 0)
_counter = [0]


def _sig(days_ago, *, symbol=None, sector=None, direction=0, event_type="General_Market",
         themes=None, base_impact=0.0, sector_score=0.0, domestic_score=0.0, overseas_score=0.0):
    _counter[0] += 1
    return NewsSignalRecord(
        id=f"s-{_counter[0]}", symbol=symbol, sector=sector, direction=direction,
        event_type=event_type, themes=themes or [], base_impact=base_impact,
        sector_score=sector_score, domestic_score=domestic_score, overseas_score=overseas_score,
        published_at=AS_OF - timedelta(days=days_ago),
    )


def test_sentiment_ratio_is_directional_vote():
    signals = [
        _sig(1, sector="반도체", direction=1),
        _sig(1, sector="반도체", direction=1),
        _sig(2, sector="반도체", direction=1),
        _sig(2, sector="반도체", direction=-1),
        _sig(3, sector="반도체", direction=0),
    ]
    # (호재 3 - 악재 1) / 전체 5 = 0.4
    assert sentiment_ratio(signals, AS_OF, "반도체", window_days=7) == 0.4


def test_sentiment_ratio_none_when_empty():
    assert sentiment_ratio([], AS_OF, "반도체") is None


def test_symbol_news_stats_mean_impact_and_count():
    signals = [
        _sig(1, symbol="005930", base_impact=1.5),
        _sig(2, symbol="005930", base_impact=0.5),
        _sig(3, symbol="005930", base_impact=-0.5),
        _sig(1, symbol="000660", base_impact=9.0),  # 다른 종목 -> 무시
    ]
    score, count = symbol_news_stats(signals, "005930", AS_OF, window_days=7)
    assert score == 0.5  # (1.5+0.5-0.5)/3
    assert count == 3


def test_symbol_news_stats_none_when_no_news():
    assert symbol_news_stats([], "005930", AS_OF) == (None, 0)


def test_macro_sentiment_index_domestic_and_overseas():
    signals = [
        _sig(1, domestic_score=1.0, overseas_score=0.0),
        _sig(2, domestic_score=0.5, overseas_score=1.5),
        _sig(3, domestic_score=0.0, overseas_score=0.0),
    ]
    assert macro_sentiment_index(signals, AS_OF, "domestic", window_days=5) == 0.5
    assert macro_sentiment_index(signals, AS_OF, "overseas", window_days=5) == 0.5


def test_momentum_change_positive_when_heating_up():
    signals = [
        # 최근 구간 [as_of-7, as_of]: 모멘텀 1.0
        _sig(1, sector="반도체", sector_score=1.0),
        _sig(2, sector="반도체", sector_score=1.0),
        # 직전 구간 [as_of-14, as_of-7]: 모멘텀 0.2
        _sig(10, sector="반도체", sector_score=0.2),
        _sig(12, sector="반도체", sector_score=0.2),
    ]
    assert momentum_change(signals, "반도체", AS_OF, window_days=7) == 0.8


def test_momentum_change_none_when_prior_missing():
    signals = [_sig(1, sector="반도체", sector_score=1.0)]  # 직전 구간 없음
    assert momentum_change(signals, "반도체", AS_OF, window_days=7) is None


def test_buzz_zscore_detects_volume_spike():
    signals = [_sig(1), _sig(1), _sig(1)]  # 직전 1일차 3건
    signals += [_sig(0), _sig(0)]           # 당일 2건
    z = buzz_zscore(signals, AS_OF, None, lookback_days=20)
    assert z is not None and z > 2.5  # (2 - 0.15)/0.6538 ≈ 2.83


def test_event_density_generalized():
    signals = [
        _sig(1, event_type="M&A_Investment"),
        _sig(1, event_type="M&A_Investment"),
        _sig(2, event_type="General_Market"),
        _sig(2, event_type="Earnings_Contract"),
    ]
    assert event_density(signals, AS_OF, ("M&A_Investment",), window_days=3) == 50.0
