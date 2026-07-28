"""한국투자증권(KIS) 어댑터 테스트.

실제 발급받은 앱키/시크릿이 없으므로 진짜 서비스 호출은 검증할 수 없다. 여기서는
1) OAuth2 토큰 발급/캐싱/모의투자 tr_id 치환(V/T 접두사)이 코드대로 동작하는지,
2) MarketDataProvider/OrderExecutionProvider 인터페이스를 만족하는지,
3) place_order 성공(rt_cd="0")/실패 매핑과 요청 body 필드(EXCG_ID_DVSN_CD 포함)가 맞는지,
4) get_balance/get_positions의 output1/output2 매핑이 맞는지,
5) 설정(KIS_APP_KEY 등) 누락 시 명확히 실패하는지
만 httpx.MockTransport로 검증한다.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from app.broker.base import OrderRequest
from app.broker.kis_adapter import KISOrderExecutionProvider
from app.broker.kis_auth import KISAuthError, KISOAuthTokenProvider, to_paper_tr_id
from app.market_data.base import MarketDataProvider
from app.market_data.kis_adapter import KISMarketDataProvider

BASE_URL = "https://openapivts.koreainvestment.com:29443"


def _token_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/oauth2/tokenP"
    return httpx.Response(200, json={"access_token": "fake-token-1", "expires_in": 3600})


def test_to_paper_tr_id_swaps_only_real_prefixes():
    assert to_paper_tr_id("TTTC0012U", is_paper=True) == "VTTC0012U"
    assert to_paper_tr_id("JTTC0012U", is_paper=True) == "VTTC0012U"
    assert to_paper_tr_id("TTTC0012U", is_paper=False) == "TTTC0012U"
    assert to_paper_tr_id("FHKST01010100", is_paper=True) == "FHKST01010100"  # 시세 조회는 치환 대상 아님


def test_token_provider_fetches_and_caches_token():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _token_handler(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISOAuthTokenProvider("key", "secret", BASE_URL, http_client=client)

    assert provider.get_token() == "fake-token-1"
    assert provider.get_token() == "fake-token-1"
    assert calls["count"] == 1  # 캐시되어 한 번만 호출됨


def test_token_provider_raises_when_access_token_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 3600})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISOAuthTokenProvider("key", "secret", BASE_URL, http_client=client)

    with pytest.raises(KISAuthError):
        provider.get_token()


def test_market_data_provider_requires_credentials():
    with pytest.raises(ValueError):
        KISMarketDataProvider("", "", BASE_URL)


def test_market_data_provider_get_price_computes_prev_close():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return _token_handler(request)
        assert request.url.path == "/uapi/domestic-stock/v1/quotations/inquire-price"
        assert request.headers.get("tr_id") == "FHKST01010100"
        return httpx.Response(200, json={"output": {"stck_prpr": "71000", "prdy_vrss": "1000", "acml_vol": "12345"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISMarketDataProvider("key", "secret", BASE_URL, http_client=client)

    assert isinstance(provider, MarketDataProvider)
    tick = provider.get_price("005930")

    assert tick.price == 71000.0
    assert tick.prev_close == 70000.0
    assert tick.volume == 12345


def test_market_data_provider_get_ohlcv_parses_candles():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return _token_handler(request)
        assert request.url.params["FID_ORG_ADJ_PRC"] == "0"
        return httpx.Response(
            200,
            json={
                "output2": [
                    {
                        "stck_bsop_date": "20250102",
                        "stck_oprc": "100",
                        "stck_hgpr": "110",
                        "stck_lwpr": "90",
                        "stck_clpr": "105",
                        "acml_vol": "1000",
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISMarketDataProvider("key", "secret", BASE_URL, http_client=client)
    bars = provider.get_ohlcv("005930", date(2025, 1, 1), date(2025, 1, 2))
    assert len(bars) == 1
    assert bars[0].close == 105.0


def test_order_execution_provider_requires_credentials():
    with pytest.raises(ValueError):
        KISOrderExecutionProvider("", "", BASE_URL, account_no="12345678-01")


def test_order_execution_provider_requires_account_format():
    with pytest.raises(ValueError):
        KISOrderExecutionProvider("key", "secret", BASE_URL, account_no="12345678")


def test_place_order_success_maps_pending_and_swaps_tr_id_for_paper():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return _token_handler(request)
        assert request.url.path == "/uapi/domestic-stock/v1/trading/order-cash"
        seen["tr_id"] = request.headers.get("tr_id")
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "msg1": "정상처리 되었습니다.",
                "output": {"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": "0000117057", "ORD_TMD": "121052"},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISOrderExecutionProvider(
        "key", "secret", BASE_URL, account_no="12345678-01", is_paper=True, http_client=client
    )

    result = provider.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=1, ref_price=71000)
    )

    assert result.status == "pending"
    assert result.order_id == "0000117057"
    assert seen["tr_id"] == "VTTC0012U"  # 매수 실전 TTTC0012U -> 모의 VTTC0012U
    assert seen["json"]["EXCG_ID_DVSN_CD"] == "KRX"
    assert seen["json"]["ORD_DVSN"] == "01"  # 시장가


def test_place_order_failure_maps_rejected_with_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return _token_handler(request)
        return httpx.Response(200, json={"rt_cd": "1", "msg1": "잔고가 부족합니다.", "msg_cd": "40910000"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISOrderExecutionProvider(
        "key", "secret", BASE_URL, account_no="12345678-01", is_paper=True, http_client=client
    )

    result = provider.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="sell", order_type="market", qty=1, ref_price=71000)
    )

    assert result.status == "rejected"
    assert result.reason == "잔고가 부족합니다."


def test_cancel_order_without_prior_place_order_raises():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    provider = KISOrderExecutionProvider(
        "key", "secret", BASE_URL, account_no="12345678-01", is_paper=True, http_client=client
    )
    with pytest.raises(ValueError):
        provider.cancel_order("unknown-order-id")


def test_get_balance_and_positions_map_output1_output2():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/tokenP":
            return _token_handler(request)
        assert request.url.path == "/uapi/domestic-stock/v1/trading/inquire-balance"
        return httpx.Response(
            200,
            json={
                "rt_cd": "0",
                "output1": [
                    {"pdno": "005930", "hldg_qty": "10", "pchs_avg_pric": "70000"},
                    {"pdno": "000660", "hldg_qty": "0", "pchs_avg_pric": "0"},
                ],
                "output2": [{"dnca_tot_amt": "5000000", "tot_evlu_amt": "5700000"}],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = KISOrderExecutionProvider(
        "key", "secret", BASE_URL, account_no="12345678-01", is_paper=True, http_client=client
    )

    balance = provider.get_balance()
    assert balance.cash == 5_000_000.0
    assert balance.equity == 5_700_000.0

    positions = provider.get_positions()
    assert len(positions) == 1  # 보유수량 0인 종목은 제외
    assert positions[0].symbol == "005930"
    assert positions[0].qty == 10
    assert positions[0].avg_price == 70000.0
