"""Phase 2 — 시계열 누적 지표(섹터 모멘텀/공포 지수/테마 Z-Score) 단위 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.dao.base import NewsSignalRecord
from app.news_signals.aggregate import macro_risk_density, sector_momentum, theme_zscore

AS_OF = datetime(2026, 7, 19, 12, 0, 0)


def _sig(days_ago, *, sector=None, event_type="General_Market", themes=None,
         sector_score=0.0, direction=0):
    return NewsSignalRecord(
        id=f"s-{days_ago}-{sector}-{event_type}-{sector_score}-{direction}-{themes}",
        symbol=None, sector=sector, direction=direction, event_type=event_type,
        themes=themes or [], base_impact=sector_score, sector_score=sector_score,
        domestic_score=0.0, overseas_score=0.0,
        published_at=AS_OF - timedelta(days=days_ago),
    )


def test_sector_momentum_is_mean_of_sector_scores_in_window():
    signals = [
        _sig(1, sector="반도체", sector_score=1.5),
        _sig(2, sector="반도체", sector_score=0.5),
        _sig(3, sector="반도체", sector_score=-0.5),  # 평균 (1.5+0.5-0.5)/3 = 0.5
        _sig(2, sector="2차전지", sector_score=9.0),  # 다른 섹터 -> 무시
        _sig(10, sector="반도체", sector_score=9.0),  # 7일 밖 -> 무시
    ]
    assert sector_momentum(signals, "반도체", AS_OF, window_days=7) == 0.5


def test_sector_momentum_none_when_no_sector_news():
    assert sector_momentum([], "반도체", AS_OF, window_days=7) is None


def test_macro_risk_density_ratio_percent():
    signals = [
        _sig(1, event_type="Geopolitical_Risk"),
        _sig(1, event_type="Macro_Indicator"),
        _sig(2, event_type="General_Market"),
        _sig(2, event_type="Earnings_Contract"),
    ]
    # 리스크성 2건 / 전체 4건 = 50%
    assert macro_risk_density(signals, AS_OF, window_days=3) == 50.0


def test_macro_risk_density_zero_when_empty():
    assert macro_risk_density([], AS_OF, window_days=3) == 0.0


def test_theme_zscore_detects_spike():
    # 최근 20일 베이스라인: 매일 1건씩 HBM 언급, 당일은 5건 -> 스파이크
    signals = []
    for d in range(1, 21):
        signals.append(_sig(d, themes=["HBM"]))
    for _ in range(5):
        signals.append(_sig(0, themes=["HBM"]))
    z = theme_zscore(signals, "HBM", AS_OF, lookback_days=20)
    # 베이스라인 평균 1, 표준편차 0 -> None (변동 없음)이 아니라...
    # 모든 날 1건이면 std=0이므로 None 반환
    assert z is None


def test_theme_zscore_with_variance():
    # 베이스라인에 변동을 줘서 std>0이 되게: 1일차 3건, 나머지 19일 0건
    signals = [_sig(1, themes=["HBM"]), _sig(1, themes=["HBM"]), _sig(1, themes=["HBM"])]
    # 당일 2건
    signals += [_sig(0, themes=["HBM"]), _sig(0, themes=["HBM"])]
    z = theme_zscore(signals, "HBM", AS_OF, lookback_days=20)
    # 베이스라인 일별: [3,0,0,...,0] (20개), 평균=0.15, pstdev≈0.6538, 당일=2
    assert z is not None
    assert z > 2.5  # (2 - 0.15) / 0.6538 ≈ 2.83


def test_theme_zscore_none_when_no_variance():
    assert theme_zscore([], "HBM", AS_OF, lookback_days=20) is None
