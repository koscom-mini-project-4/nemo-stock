"""embeddings.py(nemo-stock 통합 시 신규 추가) 회귀 테스트 — 클러스터 후보를 임베딩 유사도
top-K로 사전 필터링해 call_ai() 프롬프트가 뉴스 유입량과 무관하게 일정 크기를 유지하는지
검증한다. VENDOR_NOTES.md 참조.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.vendor.news_classifier import classifier, db, embeddings, pipeline
from app.vendor.news_classifier.config import CLUSTER_CANDIDATE_TOP_K


def _fake_embeddings_response(vector: list[float], prompt_tokens: int = 5) -> MagicMock:
    resp = MagicMock()
    resp.data = [MagicMock(embedding=vector)]
    resp.usage = MagicMock(prompt_tokens=prompt_tokens, total_tokens=prompt_tokens)
    return resp


def test_cosine_similarity_basic_cases():
    assert embeddings.cosine_similarity([1, 0], [1, 0]) == 1.0
    assert embeddings.cosine_similarity([1, 0], [0, 1]) == 0.0
    assert embeddings.cosine_similarity([1, 0], [-1, 0]) == -1.0
    assert embeddings.cosine_similarity(None, [1, 0]) == -1.0
    assert embeddings.cosine_similarity([1, 0], []) == -1.0


def test_top_k_similar_ranks_by_similarity_and_caps_at_k():
    candidates = [
        {"id": 1, "embedding": [1.0, 0.0]},   # 완전 일치
        {"id": 2, "embedding": [0.0, 1.0]},   # 직교(무관)
        {"id": 3, "embedding": [0.9, 0.1]},   # 거의 일치
        {"id": 4, "embedding": None},          # 임베딩 없음(마이그레이션 이전 데이터 등)
    ]
    result = embeddings.top_k_similar([1.0, 0.0], candidates, k=2)
    assert [c["id"] for c in result] == [1, 3]


def test_top_k_similar_k_zero_or_no_candidates_returns_empty():
    assert embeddings.top_k_similar([1.0, 0.0], [], k=5) == []
    assert embeddings.top_k_similar([1.0, 0.0], [{"id": 1, "embedding": [1.0, 0.0]}], k=0) == []


def test_embed_calls_openai_and_reports_usage(monkeypatch):
    fake_client = MagicMock()
    fake_client.embeddings.create = MagicMock(return_value=_fake_embeddings_response([0.1, 0.2]))
    monkeypatch.setattr(embeddings, "_client_once", lambda api_key=None: fake_client)
    monkeypatch.setattr(classifier, "_usage_sink", None)

    calls: list[tuple] = []
    classifier.set_usage_sink(lambda *args: calls.append(args))
    try:
        vector = embeddings.embed("삼성전자, HBM 증설 발표", api_key="sk-test")
    finally:
        classifier.set_usage_sink(None)

    assert vector == [0.1, 0.2]
    fake_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small", input="삼성전자, HBM 증설 발표"
    )
    assert calls == [("newsstock_embed", "text-embedding-3-small", 5, 0, 5)]


def test_classify_news_only_sends_top_k_candidates_to_call_ai(monkeypatch):
    """보관기간 내 클러스터가 CLUSTER_CANDIDATE_TOP_K보다 많아도 call_ai()에는 top-K만 전달돼야
    한다 — 이게 핵심 회귀 대상(전체 후보를 프롬프트에 다 넣던 원래 문제)."""
    conn = db.connect(":memory:")
    now = "2026-07-29 12:00:00"

    # 후보를 top-K보다 많이 만들어 둔다. 뒤쪽 클러스터일수록 쿼리 임베딩과 더 비슷하게 만든다.
    total = CLUSTER_CANDIDATE_TOP_K + 5
    cluster_ids = []
    for i in range(total):
        cid = db.create_cluster(conn, f"클러스터 {i}", now, 0.0, embedding=[float(i), 1.0])
        cluster_ids.append(cid)
    closest_ids = set(cluster_ids[-CLUSTER_CANDIDATE_TOP_K:])  # embedding=[total-1,1] 방향에 가장 가까움

    captured = {}

    def fake_embed(text, api_key=None):
        return [float(total), 1.0]  # 마지막 클러스터들과 가장 유사한 방향

    def fake_call_ai(news, candidates, model=None, api_key=None):
        captured["candidates"] = candidates
        return {"cluster_id": None, "representative_title": news["title"], "strength": 0.0, "items": []}

    monkeypatch.setattr(pipeline.embeddings, "embed", fake_embed)
    monkeypatch.setattr(pipeline, "call_ai", fake_call_ai)

    pipeline.classify_news(
        conn,
        {"url_hash": "new1", "url": "u", "title": "새 뉴스", "published_at": now, "content": "c"},
    )

    assert len(captured["candidates"]) == CLUSTER_CANDIDATE_TOP_K
    assert {c["id"] for c in captured["candidates"]} == closest_ids
    conn.close()
