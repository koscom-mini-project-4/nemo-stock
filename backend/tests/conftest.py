from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.nodes import load_all_nodes

load_all_nodes()


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("database_url", f"sqlite:///{db_path}")
    monkeypatch.setenv("newsstock_db_path", str(tmp_path / f"test_newsstock_{uuid.uuid4().hex}.db"))
    monkeypatch.setenv("scheduler_tick_seconds", "0.1")
    # 테스트는 개발자 로컬 backend/.env에 실제 키/provider가 들어있는지 여부와 무관하게
    # 결정적으로 동작해야 한다. "키 미설정" 경로를 검증하는 테스트가 로컬 .env의 실제 키를
    # 우연히 읽어버리지 않도록 명시적으로 비워 OS 환경변수(우선순위가 .env보다 높음)로
    # 덮어쓴다. market_data_provider/order_provider/ai_provider 자체도 강제로 dummy/openai로
    # 되돌린다 — 크리덴셜만 비우고 provider 선택은 그대로 두면, 로컬 .env가 실사용을 위해
    # koscom/kis 등으로 설정돼 있을 때 build_container()가 크리덴셜 누락으로 RuntimeError를
    # 내며 거의 모든 통합 테스트가 fixture 단계에서 깨진다(실제로 겪은 문제).
    monkeypatch.setenv("market_data_provider", "dummy")
    monkeypatch.setenv("order_provider", "dummy")
    monkeypatch.setenv("ai_provider", "openai")
    monkeypatch.setenv("openai_api_key", "")
    monkeypatch.setenv("anthropic_api_key", "")
    monkeypatch.setenv("dart_api_key", "")
    monkeypatch.setenv("data_go_kr_service_key", "")
    monkeypatch.setenv("toss_client_id", "")
    monkeypatch.setenv("toss_client_secret", "")
    monkeypatch.setenv("koscom_cust_id", "")
    monkeypatch.setenv("koscom_auth_key", "")
    monkeypatch.setenv("kis_app_key", "")
    monkeypatch.setenv("kis_app_secret", "")
    monkeypatch.setenv("kis_account_no", "")
    # 백테스트 자동 시세 수집(네이버 API 실호출)은 기본적으로 꺼서 테스트를 오프라인/결정적으로 유지한다.
    # 관련 유닛/통합 테스트는 이 값을 개별적으로 true로 오버라이드하고 클라이언트도 함께 모킹한다.
    monkeypatch.setenv("auto_ingest_prices", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

    get_settings.cache_clear()


@pytest.fixture()
def auth_headers(app_client: TestClient) -> dict[str, str]:
    resp = app_client.post("/auth/login", json={"username": "admin", "password": "admin1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
