from __future__ import annotations

from app.ai.scoring_cache import PROMPT_VERSION, get_or_compute_sentiment_score
from app.dao.memory.repositories import InMemoryAIScoreCacheRepository
from tests.unit.ai_test_doubles import FakeAIClient


def test_cache_miss_calls_ai_and_stores_result():
    cache = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": 72, "summary": "긍정적 실적 발표"}])

    result = get_or_compute_sentiment_score(cache, ai_client, "news", "news-1", "실적 서프라이즈 발표")

    assert result["score"] == 72.0
    assert result["summary"] == "긍정적 실적 발표"
    assert len(ai_client.calls) == 1
    cached = cache.get("news", "news-1", PROMPT_VERSION, ai_client.model_name)
    assert cached is not None
    assert cached.score_json["score"] == 72.0


def test_cache_hit_does_not_call_ai_again():
    cache = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": 50, "summary": "중립"}])

    first = get_or_compute_sentiment_score(cache, ai_client, "disclosure", "d-1", "유상증자 결정")
    assert len(ai_client.calls) == 1

    # 두 번째 호출은 캐시에서 바로 반환되어야 하고, FakeAIClient에는 응답이 남아있지 않아도 에러가 나면 안 된다.
    second = get_or_compute_sentiment_score(cache, ai_client, "disclosure", "d-1", "유상증자 결정")
    assert second == first
    assert len(ai_client.calls) == 1  # 추가 호출 없음


def test_different_subject_ids_are_scored_independently():
    cache = InMemoryAIScoreCacheRepository()
    ai_client = FakeAIClient(responses=[{"score": 10, "summary": "a"}, {"score": -30, "summary": "b"}])

    r1 = get_or_compute_sentiment_score(cache, ai_client, "news", "news-a", "텍스트 A")
    r2 = get_or_compute_sentiment_score(cache, ai_client, "news", "news-b", "텍스트 B")

    assert r1["score"] == 10.0
    assert r2["score"] == -30.0
    assert len(ai_client.calls) == 2
