"""API 통합 테스트: 로그인 -> 워크플로 생성 -> 검증 -> 테스트 실행(디버그 이벤트 확인).

기획서 logic_sample.png의 흐름(스케줄러->시세->조건->[뉴스/AI]->매수)을 Phase 1 범위(뉴스/AI 노드 제외)로
축소해 스케줄러->시세->조건->매수 흐름이 오버라이드 값에 따라 올바르게 매수까지 도달하는지 검증한다.
뉴스/공시/AI 노드가 추가되는 Phase 3에서 원본 시나리오 그대로 재검증한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _workflow_payload() -> dict:
    return {
        "name": "가격 상승 시 매수",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
                {"id": "n2", "type": "data.price", "params": {}},
                {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
                {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
                {"from": "n3", "to": "n4"},
            ],
        },
    }


def test_full_workflow_create_validate_and_test_run(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    assert create_resp.status_code == 201, create_resp.text
    workflow_id = create_resp.json()["id"]

    validate_resp = app_client.post(f"/workflows/{workflow_id}/validate", headers=auth_headers)
    assert validate_resp.status_code == 200
    validation = validate_resp.json()
    assert validation["valid"] is True
    assert validation["execution_order"] == ["n1", "n2", "n3", "n4"]

    # 상승(price>prev_close) 오버라이드 -> if_else 통과 -> 매수 체결까지 도달해야 한다.
    run_resp = app_client.post(
        f"/workflows/{workflow_id}/run",
        json={"overrides": {"n2": {"005930": {"price": 71000, "prev_close": 70000}}}},
        headers=auth_headers,
    )
    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    assert result["status"] == "success"
    assert result["final_symbols"]["005930"]["order_status"] == "filled"

    node_ids_seen = {e["node_id"] for e in result["events"]}
    assert node_ids_seen == {"n1", "n2", "n3", "n4"}


def test_test_run_with_target_node_id_runs_only_ancestors(app_client: TestClient, auth_headers: dict):
    """노드 단독 테스트(§0-9): target_node_id를 주면 그 노드까지만 실행하고 하류(매수 n4)는
    실행되지 않는다."""
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    run_resp = app_client.post(
        f"/workflows/{workflow_id}/run",
        json={
            "overrides": {"n2": {"005930": {"price": 71000, "prev_close": 70000}}},
            "target_node_id": "n3",
        },
        headers=auth_headers,
    )
    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    node_ids_seen = {e["node_id"] for e in result["events"]}
    assert node_ids_seen == {"n1", "n2", "n3"}
    assert "order_status" not in result["final_symbols"]["005930"]  # n4가 실행되지 않았어야 한다


def test_test_run_with_unknown_target_node_id_returns_422(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    run_resp = app_client.post(
        f"/workflows/{workflow_id}/run",
        json={"target_node_id": "does-not-exist"},
        headers=auth_headers,
    )
    assert run_resp.status_code == 422


def test_test_run_condition_fail_blocks_execution(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    # 하락(price<prev_close) 오버라이드 -> if_else 탈락 -> 매수 노드까지 종목이 전달되지 않아야 한다.
    run_resp = app_client.post(
        f"/workflows/{workflow_id}/run",
        json={"overrides": {"n2": {"005930": {"price": 69000, "prev_close": 70000}}}},
        headers=auth_headers,
    )
    assert run_resp.status_code == 200, run_resp.text
    result = run_resp.json()
    assert result["final_symbols"] == {}


def test_pnl_summary_reflects_test_run_fill(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    run_resp = app_client.post(
        f"/workflows/{workflow_id}/run",
        json={"overrides": {"n2": {"005930": {"price": 71000, "prev_close": 70000}}}},
        headers=auth_headers,
    )
    assert run_resp.status_code == 200, run_resp.text
    assert run_resp.json()["final_symbols"]["005930"]["order_status"] == "filled"

    pnl_resp = app_client.get("/workflows/pnl-summary", headers=auth_headers)
    assert pnl_resp.status_code == 200, pnl_resp.text
    entries = {e["workflow_id"]: e for e in pnl_resp.json()}
    entry = entries[workflow_id]
    assert entry["trade_count"] == 1
    assert entry["total_invested"] == 71000  # qty=1 @ 71000
    assert entry["realized_pnl"] == 0  # 매도 없음


def test_activate_requires_valid_graph(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.post("/workflows", json=_workflow_payload(), headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    activate_resp = app_client.put(f"/workflows/{workflow_id}", json={"status": "active"}, headers=auth_headers)
    assert activate_resp.status_code == 200
    assert activate_resp.json()["status"] == "active"


def test_activate_rejects_invalid_graph(app_client: TestClient, auth_headers: dict):
    payload = _workflow_payload()
    payload["graph"]["nodes"].pop()  # execution 노드 제거 -> logic.if_else가 고아 노드는 아니지만 그래프는 여전히 유효할 수 있음
    payload["graph"]["edges"] = [e for e in payload["graph"]["edges"] if e["to"] != "n4"]
    create_resp = app_client.post("/workflows", json=payload, headers=auth_headers)
    workflow_id = create_resp.json()["id"]

    # 스케줄러 노드를 2개로 만들어 명백히 invalid하게 만든다.
    bad_graph = payload["graph"]
    bad_graph["nodes"].append({"id": "n_extra_sched", "type": "scheduler.interval", "params": {"interval_sec": 1, "universe": "000660"}})
    update_resp = app_client.put(
        f"/workflows/{workflow_id}", json={"graph": bad_graph, "status": "active"}, headers=auth_headers
    )
    assert update_resp.status_code == 422
