"""Toss증권 Open API 기반 실시세 어댑터 (스켈레톤, 미검증).

DESIGN.md §0/§6 결정 사항: 실제 승인된 API 키가 없어 호출 검증은 하지 못했다.
이 클래스는 MarketDataProvider 인터페이스를 만족시키는 구조(요청 헤더/인증 흐름)만
갖추고 있으며, 실제 사용 전 아래 엔드포인트 경로/응답 필드명을 공식 OpenAPI 명세
(https://developers.tossinvest.com/docs)로 검증/교체해야 한다.

확인된 사실(공개 요약 정보 기준): REST API, OAuth2 Client Credentials 인증,
시세/호가/캔들/체결 등 시장 데이터 엔드포인트 제공. 정확한 경로/필드명은
사전신청 승인 후 명세서에서 확인 필요.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from app.broker.toss_auth import TossOAuthTokenProvider
from app.market_data.base import Bar, MarketDataProvider, OrderBook, OrderBookLevel, PriceTick

# TODO: 아래 경로는 최선 추정치이며 공식 명세로 교체 필요
QUOTE_PATH = "/api/v1/quotes/{symbol}"
ORDERBOOK_PATH = "/api/v1/orderbook/{symbol}"
CANDLES_PATH = "/api/v1/candles/{symbol}"


class TossInvestMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError(
                "TossInvestMarketDataProvider 사용에는 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET 설정이 필요합니다."
            )
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._auth = TossOAuthTokenProvider(client_id, client_secret, base_url, http_client=self._client)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = self._client.get(
            f"{self._base_url}{path}", params=params, headers=self._auth.auth_header()
        )
        response.raise_for_status()
        return response.json()

    def get_price(self, symbol: str) -> PriceTick:
        data = self._get(QUOTE_PATH.format(symbol=symbol))
        return PriceTick(
            symbol=symbol,
            price=float(data["price"]),
            prev_close=float(data.get("prevClose", data["price"])),
            volume=int(data.get("volume", 0)),
            timestamp=datetime.now(),
        )

    def get_orderbook(self, symbol: str) -> OrderBook:
        data = self._get(ORDERBOOK_PATH.format(symbol=symbol))
        bids = [OrderBookLevel(price=float(lv["price"]), qty=int(lv["qty"])) for lv in data.get("bids", [])]
        asks = [OrderBookLevel(price=float(lv["price"]), qty=int(lv["qty"])) for lv in data.get("asks", [])]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.now())

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        data = self._get(
            CANDLES_PATH.format(symbol=symbol),
            params={"start": start.isoformat(), "end": end.isoformat()},
        )
        return [
            Bar(
                symbol=symbol,
                trade_date=datetime.fromisoformat(c["date"]).date(),
                open=float(c["open"]),
                high=float(c["high"]),
                low=float(c["low"]),
                close=float(c["close"]),
                volume=int(c["volume"]),
            )
            for c in data.get("candles", [])
        ]
