"""GET /data/news/pending, GET /data/news/analyzed — 관리자 페이지 "미분석 뉴스"/"분석된
뉴스" 섹션(§0-12)이 쓰는 조회 전용 엔드포인트. FakeNewsTrader로 실제 크롤링/OpenAI 없이
검증한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory


def test_news_pending_returns_count_and_items(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(
        pending=[
            {"url_hash": "p1", "url": "https://x", "title": "미분석 기사", "published_at": "2026-07-28 09:00:00"},
        ]
    )
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get("/data/news/pending", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["title"] == "미분석 기사"
    assert trader.closed is True


def test_news_analyzed_returns_items(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(
        analyzed=[
            {
                "url_hash": "a1", "title": "분석된 기사", "date": "2026-07-28 09:00:00",
                "cluster_id": 1, "representative_title": "분석된 기사", "strength": 0.5,
                "stocks": ["삼성전자"], "sectors": [], "macros": [],
            }
        ]
    )
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get("/data/news/analyzed", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["stocks"] == ["삼성전자"]
