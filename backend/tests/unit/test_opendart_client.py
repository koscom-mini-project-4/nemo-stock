from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.data_ingestion.opendart_client import OpenDartAPIError, OpenDartClient


def _make_client(handler) -> OpenDartClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return OpenDartClient(api_key="dummy-key", http_client=http_client)


def test_fetch_disclosures_filters_by_stock_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "000",
                "message": "정상",
                "page_no": 1,
                "total_page": 1,
                "list": [
                    {
                        "rcept_no": "20250101000001", "corp_code": "00126380", "corp_name": "삼성전자",
                        "stock_code": "005930", "report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20250101",
                    },
                    {
                        "rcept_no": "20250101000002", "corp_code": "00164742", "corp_name": "다른회사",
                        "stock_code": "999999", "report_nm": "분기보고서", "rcept_dt": "20250101",
                    },
                ],
            },
        )

    with _make_client(handler) as client:
        items = client.fetch_disclosures(date(2025, 1, 1), date(2025, 1, 1), stock_codes=["005930"])

    assert len(items) == 1
    assert items[0].stock_code == "005930"
    assert items[0].rcept_dt == date(2025, 1, 1)


def test_fetch_disclosures_no_data_status_returns_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "013", "message": "조회된 데이타가 없습니다."})

    with _make_client(handler) as client:
        items = client.fetch_disclosures(date(2025, 1, 1), date(2025, 1, 2))
    assert items == []


def test_fetch_disclosures_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "020", "message": "요청 제한을 초과하였습니다."})

    with _make_client(handler) as client:
        with pytest.raises(OpenDartAPIError):
            client.fetch_disclosures(date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_disclosures_paginates_across_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        page_no = int(request.url.params["page_no"])
        item = {
            "rcept_no": f"2025010100000{page_no}", "corp_code": "00126380", "corp_name": "삼성전자",
            "stock_code": "005930", "report_nm": f"공시 {page_no}", "rcept_dt": "20250101",
        }
        return httpx.Response(200, json={"status": "000", "page_no": page_no, "total_page": 2, "list": [item]})

    with _make_client(handler) as client:
        items = client.fetch_disclosures(date(2025, 1, 1), date(2025, 1, 1))

    assert len(items) == 2
    assert {i.rcept_no for i in items} == {"20250101000001", "20250101000002"}
