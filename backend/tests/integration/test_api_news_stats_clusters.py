"""GET /data/news/stats, GET /data/news/clusters — 관리자 페이지의 "뉴스 분석 현황"이
사용하는 조회 전용 엔드포인트. FakeNewsTrader로 실제 크롤링/OpenAI 없이 검증한다."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory


def test_news_stats_returns_trader_overview(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(stats={"뉴스": 83, "클러스터": 12, "분류": 83})
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get("/data/news/stats", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json() == {"뉴스": 83, "클러스터": 12, "분류": 83}
    assert trader.closed is True


def test_news_clusters_returns_trader_cluster_list(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader(
        clusters=[{"id": 1, "representative_title": "코스피 급락", "first_seen_at": "2026-07-28", "strength": -1.0, "news_count": 4}]
    )
    app_client.app.state.container.news_trader_factory = FakeNewsTraderFactory(trader)

    resp = app_client.get("/data/news/clusters", params={"start": "2026-07-21", "end": "2026-07-28"}, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["representative_title"] == "코스피 급락"
    # 날짜만 넘겨도 그날 자정까지(23:59:59) 포함하도록 넓혀서 전달해야 한다(실 서버 검증 중
    # 발견한 버그 회귀 방지 — 날짜만 넘기면 그날 오후 이후 데이터가 상한에 걸려 누락됨).
    assert trader.cluster_calls == [("2026-07-21 00:00:00", "2026-07-28 23:59:59")]
