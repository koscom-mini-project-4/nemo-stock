"""KOSCOM CHECK-API 실계정 라이브 검증 (선택적).

backend/.env에 KOSCOM_CUST_ID/KOSCOM_AUTH_KEY가 설정되어 있을 때만 실행되며, 그렇지 않으면
자동으로 건너뛴다(CI나 다른 개발자 환경에서는 자격증명이 없으므로 항상 스킵됨). 실제 네트워크
호출을 수행하는 통합 테스트라 일반 유닛 테스트와 달리 결정적이지 않을 수 있다(레이트리밋,
장 운영시간 등의 영향).

이 테스트는 app_client 픽스처(테스트 격리를 위해 koscom_* 설정을 빈 값으로 강제)를 사용하지
않고, backend/.env를 직접 읽어 실제 자격증명으로 KoscomMarketDataProvider를 호출한다.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.config import Settings
from app.market_data.koscom_adapter import KoscomMarketDataProvider

_settings = Settings()  # .env를 직접 읽는다(다른 테스트의 monkeypatch 오버라이드와 무관)

pytestmark = pytest.mark.skipif(
    not _settings.koscom_cust_id or not _settings.koscom_auth_key,
    reason="KOSCOM_CUST_ID/KOSCOM_AUTH_KEY가 backend/.env에 설정되지 않아 라이브 검증을 건너뜁니다.",
)


@pytest.fixture(scope="module")
def provider() -> KoscomMarketDataProvider:
    return KoscomMarketDataProvider(
        _settings.koscom_cust_id, _settings.koscom_auth_key, _settings.koscom_base_url
    )


def test_live_get_price(provider: KoscomMarketDataProvider):
    tick = provider.get_price("005930")
    assert tick.symbol == "005930"
    assert tick.price > 0
    assert tick.volume >= 0


def test_live_get_orderbook(provider: KoscomMarketDataProvider):
    book = provider.get_orderbook("005930")
    assert book.symbol == "005930"
    assert book.asks[0].price > 0
    assert book.bids[0].price > 0


def test_live_get_ohlcv(provider: KoscomMarketDataProvider):
    end = date.today()
    start = end - timedelta(days=14)
    bars = provider.get_ohlcv("000660", start, end)
    assert len(bars) > 0
    for bar in bars:
        assert bar.symbol == "000660"
        assert bar.close > 0
