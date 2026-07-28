"""POST /data/news/update 통합 테스트. 실제 크롤링/OpenAI 없이 news_trader_factory를
FakeNewsTraderFactory로 교체한다(container.news_trader_factory를 직접 교체 —
/workflows/{id}/run과 동일하게 이 라우터도 container 속성을 직접 읽으므로 dependency_overrides가 아님).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.unit.ai_test_doubles import FakeNewsTrader, FakeNewsTraderFactory


def test_news_update_returns_result_from_trader(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)
    app_client.app.state.container.news_trader_factory = factory

    resp = app_client.post("/data/news/update", json={"force": True}, headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["skipped"] is False
    assert body["collected"] == 0
    assert trader.update_calls == [True]
    assert factory.auto_update_calls == [False]  # 라우터는 항상 auto_update=False로 트레이더를 만든다
    assert trader.closed is True


def test_news_update_passes_days_and_keywords_through_to_trader(app_client: TestClient, auth_headers: dict):
    """§0-12: "5일치만, 특정 키워드만" 같은 1회성 오버라이드가 trader.update()까지 전달돼야 한다."""
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)
    app_client.app.state.container.news_trader_factory = factory

    resp = app_client.post(
        "/data/news/update",
        json={"force": True, "days": 5, "keywords": ["하이닉스", "반도체", "삼성"]},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert trader.update_kwargs_calls == [{"days": 5, "keywords": ["하이닉스", "반도체", "삼성"]}]


def test_news_update_days_and_keywords_default_to_none(app_client: TestClient, auth_headers: dict):
    trader = FakeNewsTrader()
    factory = FakeNewsTraderFactory(trader)
    app_client.app.state.container.news_trader_factory = factory

    resp = app_client.post("/data/news/update", json={"force": True}, headers=auth_headers)

    assert resp.status_code == 200
    assert trader.update_kwargs_calls == [{"days": None, "keywords": None}]


def test_news_update_requires_auth(app_client: TestClient):
    resp = app_client.post("/data/news/update", json={"force": False})
    assert resp.status_code == 401
