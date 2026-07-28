"""정규화 영향도 지표(종목 직접 영향 / 업종 연관 영향) 단위 테스트.

두 지표는 최대 이벤트 가중치(1.8)로 나눠 -1.0 ~ +1.0 스케일을 갖는다. 임계값 0.3/0.5/0.7을
섹터·이벤트 종류와 무관하게 동일 기준으로 쓸 수 있어야 하므로 기대값을 고정해 둔다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.dao.base import NewsSignalRecord
from app.news_signals.aggregate import (
    MAX_EVENT_WEIGHT,
    sector_linked_impact,
    sector_momentum,
    symbol_direct_impact,
)

AS_OF = datetime(2026, 7, 19, 12, 0, 0)
_counter = [0]


def _sig(days_ago, *, symbol=None, sector=None, direction=0, event_type="General_Market",
         base_impact=0.0, sector_score=0.0):
    _counter[0] += 1
    return NewsSignalRecord(
        id=f"n-{_counter[0]}", symbol=symbol, sector=sector, direction=direction,
        event_type=event_type, themes=[], base_impact=base_impact,
        sector_score=sector_score, domestic_score=0.0, overseas_score=0.0,
        published_at=AS_OF - timedelta(days=days_ago),
    )


def test_max_event_weight_is_geopolitical():
    assert MAX_EVENT_WEIGHT == 1.8


def test_symbol_direct_impact_normalizes_to_unit_scale():
    # 지정학 호재 1건(base_impact=1.8) → 정규화 시 정확히 1.0(최대치)
    signals = [_sig(1, symbol="000660", base_impact=1.8, direction=1)]
    assert symbol_direct_impact(signals, "000660", AS_OF) == pytest.approx(1.0)

    # 단순 시황 호재 1건(0.3) → 0.3/1.8 ≈ 0.167. 같은 '호재'라도 강도가 구분된다.
    weak = [_sig(1, symbol="000660", base_impact=0.3, direction=1)]
    assert symbol_direct_impact(weak, "000660", AS_OF) == pytest.approx(0.3 / 1.8)


def test_symbol_direct_impact_averages_and_isolates_symbol():
    signals = [
        _sig(1, symbol="000660", base_impact=1.8),
        _sig(2, symbol="000660", base_impact=0.0),
        _sig(1, symbol="005930", base_impact=-1.8),  # 다른 종목 뉴스는 섞이면 안 된다
    ]
    assert symbol_direct_impact(signals, "000660", AS_OF) == pytest.approx(0.9 / 1.8)
    assert symbol_direct_impact(signals, "005930", AS_OF) == pytest.approx(-1.0)


def test_symbol_direct_impact_none_without_news():
    assert symbol_direct_impact([], "000660", AS_OF) is None
    # 윈도우 밖 뉴스는 없는 것과 같다
    old = [_sig(30, symbol="000660", base_impact=1.8)]
    assert symbol_direct_impact(old, "000660", AS_OF, window_days=7) is None


def test_sector_linked_impact_excludes_non_impacting_news():
    """섹터 영향 플래그가 꺼진 뉴스(sector_score=0)는 분모에서도 빠진다 — 희석되지 않는다."""
    signals = [
        _sig(1, sector="반도체", sector_score=1.8),   # 실제로 업종을 움직인 뉴스
        _sig(1, sector="반도체", sector_score=0.0),   # 반도체 언급이지만 업종 영향 없음
        _sig(2, sector="반도체", sector_score=0.0),
    ]
    # 영향 뉴스만 보면 1.8/1.8 = 1.0
    assert sector_linked_impact(signals, "반도체", AS_OF) == pytest.approx(1.0)
    # sector_momentum은 무영향 뉴스까지 분모에 넣으므로 희석된 값(1.8/3 = 0.6)이 나온다
    assert sector_momentum(signals, "반도체", AS_OF) == pytest.approx(0.6)


def test_sector_linked_impact_none_when_no_impacting_news():
    signals = [_sig(1, sector="반도체", sector_score=0.0)]
    assert sector_linked_impact(signals, "반도체", AS_OF) is None
    assert sector_linked_impact(signals, "조선", AS_OF) is None
