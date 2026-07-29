"""GET /data/news/topics, GET /data/news/topics/clusters — 관리자 페이지의 "종목/섹터/거시로부터
관련 클러스터 탐색"(§0-7, GET /data/news/clusters의 반대 방향) 기능이 쓰는 조회 전용
엔드포인트. FakeNewsTrader로 실제 크롤링/OpenAI 없이 검증한다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory


def test_news_topics_returns_keys_for_group(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(topic_keys={"A": ["삼성전자", "SK하이닉스"]})
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get(
        "/data/news/topics", params={"group": "stock", "start": "2026-07-21", "end": "2026-07-28"}, headers=auth_headers
    )

    assert resp.status_code == 200
    assert resp.json() == ["삼성전자", "SK하이닉스"]
    assert trader.keys_in_range_calls == [("A", "2026-07-21 00:00:00", "2026-07-28 23:59:59")]
    assert trader.closed is True


def test_news_topics_rejects_unknown_group(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader()
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get(
        "/data/news/topics", params={"group": "unknown", "start": "2026-07-21", "end": "2026-07-28"}, headers=auth_headers
    )

    assert resp.status_code == 400


def test_news_topic_clusters_returns_clusters_linked_to_key(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(
        topic_clusters={
            ("B", "반도체"): [
                {"cluster_id": 1, "representative_title": "반도체 업황 우려", "first_seen_at": "2026-07-27 10:00:00", "strength": -0.5, "count": 3},
            ]
        }
    )
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get(
        "/data/news/topics/clusters",
        params={"group": "sector", "key": "반도체", "start": "2026-07-21", "end": "2026-07-28"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["representative_title"] == "반도체 업황 우려"
    assert trader.clusters_for_key_calls == [("B", "반도체", "2026-07-21 00:00:00", "2026-07-28 23:59:59")]
