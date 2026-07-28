"""KOSCOM CHECK-API 어댑터 스켈레톤 테스트.

실제 승인된 cust_id/auth_key가 없으므로 진짜 서비스 호출은 검증할 수 없다. 여기서는
1) MarketDataProvider 인터페이스를 만족하는지,
2) 요청이 문서대로 POST 폼 바디(cust_id/auth_key/jcode 등)로 구성되는지,
3) 공식 문서의 "1초당 1회" 레이트리밋을 실제로 지키는지,
4) 성공/실패(success=false) 응답 처리와 설정 누락 시 실패를
httpx.MockTransport로 검증한다.
"""

from __future__ import annotations

import time
from datetime import date

import httpx
import pytest

from app.market_data.base import MarketDataProvider
from app.market_data.koscom_adapter import KoscomAPIError, KoscomMarketDataProvider


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_requires_credentials():
    with pytest.raises(ValueError):
        KoscomMarketDataProvider("", "", "https://checkapi.koscom.co.kr")


def test_implements_interface_and_sends_form_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/stock/m001/basic_info"
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.read().decode()
        return httpx.Response(
            200, json={"success": True, "results": [{"F15001": 71000, "F15472": 1000, "F15015": 12345}]}
        )

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )
    assert isinstance(provider, MarketDataProvider)

    tick = provider.get_price("005930")

    assert tick.price == 71000.0
    assert tick.prev_close == 70000.0  # F15001 - F15472
    assert tick.volume == 12345
    assert "application/x-www-form-urlencoded" in seen["content_type"]
    assert "cust_id=NS00000001" in seen["body"]
    assert "auth_key=authkey123" in seen["body"]
    assert "jcode=005930" in seen["body"]


def test_get_orderbook_parses_first_level():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/stock/m001/hoga_info"
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [{"F14501": 71100, "F14531": 71000, "F14511": 500, "F14541": 300}],
            },
        )

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )
    book = provider.get_orderbook("005930")
    assert book.asks[0].price == 71100.0
    assert book.asks[0].qty == 500
    assert book.bids[0].price == 71000.0
    assert book.bids[0].qty == 300


def test_get_ohlcv_parses_history_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/stock/m001/hist_info"
        body = request.read().decode()
        assert "sdate=20250101" in body
        assert "edate=20250102" in body
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [
                    {
                        "F12506": "20250102", "F15009": 100, "F15010": 110, "F15011": 90,
                        "F15001": 105, "F15015": 1000,
                    }
                ],
            },
        )

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )
    bars = provider.get_ohlcv("005930", date(2025, 1, 1), date(2025, 1, 2))
    assert len(bars) == 1
    assert bars[0].trade_date == date(2025, 1, 2)
    assert bars[0].close == 105.0


def test_raises_on_success_false_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": False, "message": {"errmsg": "access_denied", "desc": "User denied access"}}
        )

    provider = KoscomMarketDataProvider(
        "bad", "creds", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )
    with pytest.raises(KoscomAPIError):
        provider.get_price("005930")


def test_fetch_symbol_master_combines_kospi_and_kosdaq_code_info():
    """§0-10 폴백 소스: /stock/m001/code_info(거래소)와 /stock/m003/code_info(코스닥)를
    각각 1회씩만 불러 전 종목 코드/명을 합친다."""
    paths_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths_seen.append(request.url.path)
        if request.url.path == "/stock/m001/code_info":
            results = [
                {"F16013": "005930", "F16002": "삼성전자"},
                {"F16013": "000660", "F16002": "SK하이닉스"},
            ]
        else:
            results = [{"F16013": "066570", "F16002": "LG전자"}]
        return httpx.Response(200, json={"success": True, "results": results})

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )

    rows = provider.fetch_symbol_master()

    assert paths_seen == ["/stock/m001/code_info", "/stock/m003/code_info"]
    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["005930"] == {"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}
    assert by_symbol["000660"]["market"] == "KOSPI"
    assert by_symbol["066570"] == {"symbol": "066570", "name": "LG전자", "market": "KOSDAQ"}


def test_fetch_symbol_master_skips_rows_missing_code_or_name():
    """양쪽 시장 호출 모두 동일한 mock 응답을 주므로(핸들러가 경로를 안 봄), 필드 누락 skip
    로직만 검증한다 — 결과는 시장마다 유효한 행 1건씩, 총 2건이어야 한다."""

    def handler(request: httpx.Request) -> httpx.Response:
        results = [
            {"F16013": "005930", "F16002": "삼성전자"},
            {"F16013": "", "F16002": "코드없음"},
            {"F16013": "999999"},  # 이름 없음
        ]
        return httpx.Response(200, json={"success": True, "results": results})

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )

    rows = provider.fetch_symbol_master()

    assert len(rows) == 2
    assert all(r["symbol"] == "005930" and r["name"] == "삼성전자" for r in rows)
    assert {r["market"] for r in rows} == {"KOSPI", "KOSDAQ"}


def test_enforces_minimum_one_second_between_requests():
    call_times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        call_times.append(time.monotonic())
        return httpx.Response(200, json={"success": True, "results": [{"F15001": 100, "F15472": 0, "F15015": 1}]})

    provider = KoscomMarketDataProvider(
        "NS00000001", "authkey123", "https://checkapi.koscom.co.kr", http_client=_client(handler)
    )
    provider.get_price("005930")
    provider.get_price("000660")

    assert len(call_times) == 2
    assert call_times[1] - call_times[0] >= 0.9  # 최소 1초 간격(문서상 1초당 1회 제한) 근사 검증
