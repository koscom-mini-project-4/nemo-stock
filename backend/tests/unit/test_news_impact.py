"""Phase 1 — 단일 뉴스 충격량(Impact) 계산 단위 테스트(기대값 고정)."""

from __future__ import annotations

from app.news_signals.impact import EVENT_WEIGHTS, compute_impact, event_weight


def _classification(direction, event_type, sector=True, domestic=False, overseas=False):
    return {
        "depth_1": {"direction": direction},
        "depth_2": {
            "target_sector": "반도체",
            "is_sector_impact": sector,
            "is_domestic_impact": domestic,
            "is_overseas_impact": overseas,
        },
        "depth_3": {"themes": ["HBM"], "event_type": event_type},
    }


def test_base_impact_is_direction_times_weight():
    # M&A_Investment 가중치 1.5, direction +1 -> +1.5
    result = compute_impact(_classification(1, "M&A_Investment", sector=True, domestic=True))
    assert result["base_impact"] == 1.5
    assert result["sector_score"] == 1.5     # is_sector_impact=True
    assert result["domestic_score"] == 1.5   # is_domestic_impact=True
    assert result["overseas_score"] == 0.0   # is_overseas_impact=False


def test_negative_direction_management_risk():
    # Management_Risk 가중치 1.5, direction -1 -> -1.5 (악재 킬스위치)
    result = compute_impact(_classification(-1, "Management_Risk", sector=True))
    assert result["base_impact"] == -1.5
    assert result["sector_score"] == -1.5


def test_neutral_direction_zeroes_all_scores():
    result = compute_impact(_classification(0, "Geopolitical_Risk", sector=True, overseas=True))
    assert result["base_impact"] == 0.0
    assert result["sector_score"] == 0.0
    assert result["overseas_score"] == 0.0


def test_general_market_is_discounted():
    assert event_weight("General_Market") == 0.3
    result = compute_impact(_classification(1, "General_Market", sector=True))
    assert result["sector_score"] == 0.3


def test_unknown_event_falls_back_to_general_market_weight():
    assert event_weight("NOT_A_REAL_EVENT") == EVENT_WEIGHTS["General_Market"]
