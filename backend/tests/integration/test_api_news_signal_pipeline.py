"""koscom_nemonemo(fork) 뉴스 신호 파이프라인(§0-6) 통합 테스트.

POST /data/ingest/news/classified로 이미 분류된 뉴스를 적재 → data.sector_momentum
노드가 워크플로 테스트 실행에서 실제로 그 신호를 조회/판정하는지까지 확인한다(AI 호출 없음
— 이미 분류된 입력을 쓰므로 news_classify.py를 거치지 않는다).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_ingest_classified_news_and_sector_momentum_node_end_to_end(app_client: TestClient, auth_headers: dict):
    payload = {
        "items": [
            {
                "title": "삼성전자 HBM 대규모 수주",
                "body": "...",
                "published_at": "2026-07-28T09:00:00",
                "symbol": "005930",
                "classification": {
                    "depth_1": {"direction": 1},
                    "depth_2": {
                        "target_sector": "반도체",
                        "is_sector_impact": True,
                        "is_domestic_impact": True,
                        "is_overseas_impact": False,
                    },
                    "depth_3": {"themes": ["HBM"], "event_type": "Earnings_Contract"},
                },
            }
        ]
    }
    ingest_resp = app_client.post("/data/ingest/news/classified", json=payload, headers=auth_headers)
    assert ingest_resp.status_code == 200, ingest_resp.text
    assert ingest_resp.json()["ingested"] == 1

    wf_payload = {
        "name": "섹터 모멘텀 테스트",
        "schedule_interval_sec": 60,
        "graph": {
            "nodes": [
                {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
                {
                    "id": "n2",
                    "type": "data.sector_momentum",
                    "params": {"sector": "반도체", "window_days": 7, "condition": "leader"},
                },
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        },
    }
    wf_resp = app_client.post("/workflows", json=wf_payload, headers=auth_headers)
    assert wf_resp.status_code == 201, wf_resp.text
    workflow_id = wf_resp.json()["id"]

    run_resp = app_client.post(f"/workflows/{workflow_id}/run", json={"mode": "test"}, headers=auth_headers)
    assert run_resp.status_code == 200, run_resp.text
    body = run_resp.json()
    assert body["status"] == "success"

    node_event = next(e for e in body["events"] if e["node_id"] == "n2" and e["status"] == "success")
    symbol_data = node_event["output_snapshot"]["symbols"].get("005930")
    assert symbol_data is not None
    assert symbol_data["sector_momentum"] is not None
    decision = node_event["output_snapshot"]["meta"]["decisions"]["n2"]["005930"]
    assert decision["pass"] is True
    assert "sector_momentum" in decision["reason"]
