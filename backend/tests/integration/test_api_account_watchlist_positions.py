"""관심종목(watchlist) + 보유 포지션 직접 관리 API 테스트.

배경: "테스트 실행"이 라이브 계좌(container.broker)를 그대로 공유해, 임의 종목코드로
테스트 실행하면 실제 portfolio_positions에 잔재가 남는 문제(PWTESTQ1/PWRESTART1)가 있었다.
이 테스트는 그 잔재를 정리/정정할 수 있는 새 엔드포인트와, 보유 여부와 무관하게 종목을
추적할 수 있는 관심종목 기능을 검증한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_watchlist_add_list_remove(app_client: TestClient, auth_headers: dict):
    add_resp = app_client.post("/account/watchlist", json={"symbol": "005930"}, headers=auth_headers)
    assert add_resp.status_code == 201, add_resp.text
    assert [i["symbol"] for i in add_resp.json()] == ["005930"]

    list_resp = app_client.get("/account/watchlist", headers=auth_headers)
    assert list_resp.status_code == 200
    assert [i["symbol"] for i in list_resp.json()] == ["005930"]

    del_resp = app_client.delete("/account/watchlist/005930", headers=auth_headers)
    assert del_resp.status_code == 204

    list_resp2 = app_client.get("/account/watchlist", headers=auth_headers)
    assert list_resp2.json() == []


def test_watchlist_add_is_idempotent(app_client: TestClient, auth_headers: dict):
    app_client.post("/account/watchlist", json={"symbol": "000660"}, headers=auth_headers)
    resp = app_client.post("/account/watchlist", json={"symbol": "000660"}, headers=auth_headers)
    assert resp.status_code == 201
    assert [i["symbol"] for i in resp.json()] == ["000660"]  # 중복 추가돼도 하나만 남는다


def test_watchlist_remove_nonexistent_symbol_does_not_error(app_client: TestClient, auth_headers: dict):
    resp = app_client.delete("/account/watchlist/999999", headers=auth_headers)
    assert resp.status_code == 204


def test_position_upsert_creates_then_updates(app_client: TestClient, auth_headers: dict):
    create_resp = app_client.put(
        "/account/positions/PWTESTQ1", json={"qty": 1, "avg_price": 50000.0}, headers=auth_headers
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json() == {"symbol": "PWTESTQ1", "qty": 1, "avg_price": 50000.0}

    update_resp = app_client.put(
        "/account/positions/PWTESTQ1", json={"qty": 5, "avg_price": 51000.0}, headers=auth_headers
    )
    assert update_resp.status_code == 200
    assert update_resp.json() == {"symbol": "PWTESTQ1", "qty": 5, "avg_price": 51000.0}


def test_position_upsert_rejects_non_positive_qty(app_client: TestClient, auth_headers: dict):
    resp = app_client.put("/account/positions/005930", json={"qty": 0, "avg_price": 1000.0}, headers=auth_headers)
    assert resp.status_code == 400


def test_position_delete_removes_it_and_is_idempotent(app_client: TestClient, auth_headers: dict):
    app_client.put("/account/positions/PWRESTART1", json={"qty": 1, "avg_price": 1000.0}, headers=auth_headers)

    del_resp = app_client.delete("/account/positions/PWRESTART1", headers=auth_headers)
    assert del_resp.status_code == 204

    # 존재하지 않는 종목을 다시 삭제해도 에러 없이 넘어간다.
    del_resp2 = app_client.delete("/account/positions/PWRESTART1", headers=auth_headers)
    assert del_resp2.status_code == 204
