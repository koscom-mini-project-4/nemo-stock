from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.data_ingestion.public_data_price import PublicDataAPIError, PublicDataPriceClient


def _make_client(handler) -> PublicDataPriceClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return PublicDataPriceClient(service_key="dummy-key", http_client=http_client)


def test_fetch_daily_prices_parses_single_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "numOfRows": 500,
                        "pageNo": 1,
                        "totalCount": 2,
                        "items": {
                            "item": [
                                {
                                    "basDt": "20250102", "srtnCd": "005930", "mkp": "70000",
                                    "hipr": "71000", "lopr": "69500", "clpr": "70500", "trqu": "1000000",
                                },
                                {
                                    "basDt": "20250103", "srtnCd": "005930", "mkp": "70500",
                                    "hipr": "72000", "lopr": "70000", "clpr": "71800", "trqu": "1200000",
                                },
                            ]
                        },
                    },
                }
            },
        )

    with _make_client(handler) as client:
        bars = client.fetch_daily_prices("005930", date(2025, 1, 2), date(2025, 1, 3))

    assert len(bars) == 2
    assert bars[0].trade_date == date(2025, 1, 2)
    assert bars[0].close == 70500.0
    assert bars[0].volume == 1000000
    assert bars[1].close == 71800.0


def test_fetch_daily_prices_paginates():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page_no = int(request.url.params["pageNo"])
        calls.append(page_no)
        if page_no == 1:
            items = [{"basDt": "20250102", "mkp": "100", "hipr": "110", "lopr": "90", "clpr": "105", "trqu": "10"}]
        else:
            items = [{"basDt": "20250103", "mkp": "105", "hipr": "115", "lopr": "95", "clpr": "110", "trqu": "20"}]
        return httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"numOfRows": 1, "pageNo": page_no, "totalCount": 2, "items": {"item": items}},
                }
            },
        )

    with _make_client(handler) as client:
        bars = client.fetch_daily_prices("005930", date(2025, 1, 2), date(2025, 1, 3), num_of_rows=1)

    assert calls == [1, 2]
    assert len(bars) == 2


def test_fetch_daily_prices_raises_on_error_result_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}},
        )

    with _make_client(handler) as client:
        with pytest.raises(PublicDataAPIError):
            client.fetch_daily_prices("005930", date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_daily_prices_empty_result():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 0, "items": ""}}},
        )

    with _make_client(handler) as client:
        bars = client.fetch_daily_prices("005930", date(2025, 1, 1), date(2025, 1, 2))
    assert bars == []
