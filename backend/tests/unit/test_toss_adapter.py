"""Toss증권 어댑터 스켈레톤 테스트.

실제 승인된 API 키가 없으므로 진짜 서비스 호출은 검증할 수 없다. 여기서는
1) OAuth2 Client Credentials 토큰 발급/캐싱/헤더 구성이 코드대로 동작하는지,
2) MarketDataProvider/OrderExecutionProvider 인터페이스를 만족하는지,
3) 설정(TOSS_CLIENT_ID 등) 누락 시 명확히 실패하는지
만 httpx.MockTransport로 검증한다.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.broker.base import OrderRequest
from app.broker.toss_adapter import TossInvestOrderExecutionProvider
from app.broker.toss_auth import TossAuthError, TossOAuthTokenProvider
from app.market_data.base import MarketDataProvider
from app.market_data.toss_adapter import TossInvestMarketDataProvider


def _token_handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/oauth2/token"
    return httpx.Response(200, json={"access_token": "fake-token-1", "expires_in": 3600})


def test_token_provider_fetches_and_caches_token():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _token_handler(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TossOAuthTokenProvider("id", "secret", "https://apis.tossinvest.com", http_client=client)

    token1 = provider.get_token()
    token2 = provider.get_token()

    assert token1 == "fake-token-1"
    assert token2 == "fake-token-1"
    assert calls["count"] == 1  # 캐시되어 한 번만 호출됨


def test_token_provider_raises_when_access_token_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 3600})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TossOAuthTokenProvider("id", "secret", "https://apis.tossinvest.com", http_client=client)

    with pytest.raises(TossAuthError):
        provider.get_token()


def test_market_data_provider_requires_credentials():
    with pytest.raises(ValueError):
        TossInvestMarketDataProvider("", "", "https://apis.tossinvest.com")


def test_market_data_provider_implements_interface_and_sends_bearer_token():
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_handler(request)
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"price": 71000, "prevClose": 70000, "volume": 12345})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TossInvestMarketDataProvider("id", "secret", "https://apis.tossinvest.com", http_client=client)

    assert isinstance(provider, MarketDataProvider)
    tick = provider.get_price("005930")

    assert tick.price == 71000.0
    assert tick.volume == 12345
    assert seen_headers.get("authorization") == "Bearer fake-token-1"


def test_market_data_provider_get_ohlcv_parses_candles():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_handler(request)
        return httpx.Response(
            200,
            json={
                "candles": [
                    {"date": "2025-01-02", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TossInvestMarketDataProvider("id", "secret", "https://apis.tossinvest.com", http_client=client)
    bars = provider.get_ohlcv("005930", date(2025, 1, 1), date(2025, 1, 2))
    assert len(bars) == 1
    assert bars[0].close == 105.0


def test_order_execution_provider_requires_credentials():
    with pytest.raises(ValueError):
        TossInvestOrderExecutionProvider("", "", "https://apis.tossinvest.com", account_id="acc-1")


def test_order_execution_provider_sends_account_header_on_place_order():
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth2/token":
            return _token_handler(request)
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"orderId": "ord-1", "price": 71000, "status": "filled"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TossInvestOrderExecutionProvider(
        "id", "secret", "https://apis.tossinvest.com", account_id="acc-1", http_client=client
    )

    result = provider.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=1)
    )

    assert result.order_id == "ord-1"
    assert result.status == "filled"
    assert seen_headers.get("x-tossinvest-account") == "acc-1"
    assert seen_headers.get("authorization") == "Bearer fake-token-1"
