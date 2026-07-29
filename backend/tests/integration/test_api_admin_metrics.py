"""GET /admin/metrics 통합 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dao.base import AIUsageRecord


def test_admin_metrics_combines_backtest_count_and_ai_usage(app_client: TestClient, auth_headers: dict):
    container = app_client.app.state.container
    container.ai_usage_repo.save(
        AIUsageRecord(id="u1", purpose="workflow_draft", model="gpt-5.6-luna",
                      prompt_tokens=100, completion_tokens=20, total_tokens=120)
    )
    container.ai_usage_repo.save(
        AIUsageRecord(id="u2", purpose="newsstock_classify", model="gpt-4o-mini",
                      prompt_tokens=50, completion_tokens=10, total_tokens=60)
    )

    resp = app_client.get("/admin/metrics", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["backtest_count"] == 0
    assert body["ai_usage"]["total_calls"] == 2
    assert body["ai_usage"]["total_tokens"] == 180
    purposes = {b["purpose"] for b in body["ai_usage"]["by_purpose"]}
    assert purposes == {"workflow_draft", "newsstock_classify"}
