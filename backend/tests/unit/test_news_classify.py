"""app.ai.news_classify — AI 뉴스 분류(라벨링) 로직 + 정규화 + 캐시 단위 테스트.

분류는 노드가 아니라 수집 시점 배경 작업으로 쓰인다(app/news_signals 참조).
여기서는 AI 응답을 고정 스키마로 정규화하는 계층과 캐시 재사용만 검증한다.
"""

from __future__ import annotations

from app.ai.news_classify import (
    DEFAULT_EVENT_TYPE,
    classify_news,
    get_or_compute_news_classification,
    normalize_classification,
)
from app.dao.memory.repositories import InMemoryAIScoreCacheRepository
from tests.unit.ai_test_doubles import FakeAIClient


def test_normalize_full_valid_response():
    raw = {
        "depth_1": {"direction": 1},
        "depth_2": {
            "target_sector": "반도체",
            "is_sector_impact": True,
            "is_domestic_impact": False,
            "is_overseas_impact": True,
        },
        "depth_3": {"themes": ["HBM", "전고체"], "event_type": "Earnings_Contract"},
    }
    assert normalize_classification(raw) == raw


def test_normalize_coerces_out_of_range_and_invalid_values():
    raw = {
        "depth_1": {"direction": 5},  # 범위 밖 -> 1
        "depth_2": {
            "target_sector": "null",  # -> None
            "is_sector_impact": "true",  # 문자열 -> bool
            "is_domestic_impact": 1,
            # is_overseas_impact 누락 -> False
        },
        "depth_3": {
            "themes": ["HBM", "월드컵", "전기차"],  # 잡음(월드컵) 드롭 + 최대 2개
            "event_type": "Unknown_Event",  # 허용 밖 -> 기본값
        },
    }
    result = normalize_classification(raw)
    assert result["depth_1"]["direction"] == 1
    assert result["depth_2"]["target_sector"] is None
    assert result["depth_2"]["is_sector_impact"] is True
    assert result["depth_2"]["is_domestic_impact"] is True
    assert result["depth_2"]["is_overseas_impact"] is False
    assert result["depth_3"]["themes"] == ["HBM", "전기차"]  # 통제 어휘로 정규화
    assert result["depth_3"]["event_type"] == DEFAULT_EVENT_TYPE


def test_normalize_negative_direction_and_empty_dict():
    assert normalize_classification({"depth_1": {"direction": -3}})["depth_1"]["direction"] == -1
    empty = normalize_classification({})
    assert empty["depth_1"]["direction"] == 0
    assert empty["depth_2"]["target_sector"] is None
    assert empty["depth_3"]["themes"] == []
    assert empty["depth_3"]["event_type"] == DEFAULT_EVENT_TYPE


def test_non_economic_gate_zeroes_everything():
    raw = {
        "depth_1": {"direction": -1},  # AI가 방향을 붙였어도
        "depth_2": {"target_sector": "금융", "is_sector_impact": True,
                    "is_domestic_impact": True, "is_overseas_impact": True},
        "depth_3": {"themes": ["HBM"], "event_type": "Non_Economic"},
    }
    r = normalize_classification(raw)
    assert r["depth_1"]["direction"] == 0
    assert r["depth_2"] == {"target_sector": None, "is_sector_impact": False,
                            "is_domestic_impact": False, "is_overseas_impact": False}
    assert r["depth_3"]["themes"] == []
    assert r["depth_3"]["event_type"] == "Non_Economic"


def test_classify_news_normalizes_ai_output():
    ai = FakeAIClient(responses=[{"depth_1": {"direction": "1"}, "depth_3": {"event_type": "M&A_Investment"}}])
    result = classify_news(ai, "삼성전자, HBM 증설 위해 대규모 투자 발표")
    assert result["depth_1"]["direction"] == 1
    assert result["depth_3"]["event_type"] == "M&A_Investment"


def test_cache_reuse_avoids_second_ai_call():
    cache_repo = InMemoryAIScoreCacheRepository()
    ai = FakeAIClient(responses=[{"depth_1": {"direction": 1}}])  # 응답 1개만 준비
    first = get_or_compute_news_classification(cache_repo, ai, subject_id="news-1", text="호재 뉴스")
    second = get_or_compute_news_classification(cache_repo, ai, subject_id="news-1", text="호재 뉴스")
    assert first == second
    assert len(ai.calls) == 1  # 두 번째는 캐시 히트 -> AI 미호출
