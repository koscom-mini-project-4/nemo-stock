"""Toss증권 Open API 기반 주문 실행 어댑터 (스켈레톤, 미검증).

DESIGN.md §0/§6 결정 사항: 실제 승인된 API 키가 없어 호출 검증은 하지 못했다.
계좌 관련 호출에는 공개 요약 정보에 언급된 X-Tossinvest-Account 헤더가 필요하다고
알려져 있으나, 정확한 요청/응답 스키마는 공식 명세(https://developers.tossinvest.com/docs)
승인 후 확인 후 교체해야 한다.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.broker.base import Balance, OrderExecutionProvider, OrderRequest, OrderResult, Position
from app.broker.toss_auth import TossOAuthTokenProvider

# TODO: 아래 경로/페이로드는 최선 추정치이며 공식 명세로 교체 필요
ORDERS_PATH = "/api/v1/orders"
ORDER_DETAIL_PATH = "/api/v1/orders/{order_id}"
BALANCE_PATH = "/api/v1/accounts/{account}/balance"
POSITIONS_PATH = "/api/v1/accounts/{account}/positions"


class TossInvestOrderExecutionProvider(OrderExecutionProvider):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str,
        account_id: str,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError(
                "TossInvestOrderExecutionProvider 사용에는 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET 설정이 필요합니다."
            )
        self._account_id = account_id
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._auth = TossOAuthTokenProvider(client_id, client_secret, base_url, http_client=self._client)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _headers(self) -> dict[str, str]:
        headers = self._auth.auth_header()
        headers["X-Tossinvest-Account"] = self._account_id
        return headers

    def place_order(self, order: OrderRequest) -> OrderResult:
        payload = {
            "symbol": order.symbol,
            "side": order.side,
            "orderType": order.order_type,
            "qty": order.qty,
        }
        if order.limit_price is not None:
            payload["price"] = order.limit_price

        response = self._client.post(f"{self._base_url}{ORDERS_PATH}", json=payload, headers=self._headers())
        response.raise_for_status()
        data = response.json()
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            price=float(data.get("price", order.limit_price or 0.0)),
            status=data.get("status", "pending"),  # type: ignore[arg-type]
            filled_at=datetime.now() if data.get("status") == "filled" else None,
        )

    def cancel_order(self, order_id: str) -> None:
        response = self._client.delete(
            f"{self._base_url}{ORDER_DETAIL_PATH.format(order_id=order_id)}", headers=self._headers()
        )
        response.raise_for_status()

    def get_balance(self) -> Balance:
        data = self._client.get(
            f"{self._base_url}{BALANCE_PATH.format(account=self._account_id)}", headers=self._headers()
        )
        data.raise_for_status()
        body = data.json()
        return Balance(cash=float(body.get("cash", 0)), equity=float(body.get("equity", 0)))

    def get_positions(self) -> list[Position]:
        response = self._client.get(
            f"{self._base_url}{POSITIONS_PATH.format(account=self._account_id)}", headers=self._headers()
        )
        response.raise_for_status()
        body = response.json()
        return [
            Position(symbol=p["symbol"], qty=int(p["qty"]), avg_price=float(p["avgPrice"]))
            for p in body.get("positions", [])
        ]
