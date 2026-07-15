"""KOSCOM CHECK-API 기반 실시세 어댑터 (스켈레톤, 미검증).

DESIGN.md의 Toss 어댑터와 같은 성격의 제약: CHECK-API는 코스콤 "CHECK 단말" 구독 고객에게
발급되는 cust_id/auth_key가 있어야 호출 가능한 유료 서비스이며, 이 PoC에는 실제 자격증명이
없어 호출 검증을 하지 못했다. 다만 아래 엔드포인트/필드명은 실제로 렌더링해 확인한 공식 문서
(https://checkapi.koscom.co.kr, 2026-07-15 조사)를 그대로 반영한 것으로, 조사 근거와 원문은
docs/koscom-api/README.md 및 같은 폴더의 raw-*.txt에 보관되어 있다.

공식 문서 명시 제약:
- HTTPS + POST만 지원(GET/HTTP 미지원, 보안상 이유)
- 인증 파라미터는 JSON이 아닌 폼 바디(요청 예제가 requests의 data=payload 사용)
- 데이터 조회는 1초당 1회를 초과할 수 없음 -> 이 클래스는 요청 간 최소 간격을 강제한다.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime

import httpx

from app.market_data.base import Bar, MarketDataProvider, OrderBook, OrderBookLevel, PriceTick

BASIC_INFO_PATH = "/stock/m001/basic_info"  # 현재가 등 기본정보
HOGA_INFO_PATH = "/stock/m001/hoga_info"  # 호가정보
HIST_INFO_PATH = "/stock/m001/hist_info"  # 일별(과거) 정보

MIN_REQUEST_INTERVAL_SEC = 1.0


class KoscomAPIError(RuntimeError):
    pass


class KoscomMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        cust_id: str,
        auth_key: str,
        base_url: str,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not cust_id or not auth_key:
            raise ValueError(
                "KoscomMarketDataProvider 사용에는 KOSCOM_CUST_ID/KOSCOM_AUTH_KEY 설정이 필요합니다."
            )
        self._cust_id = cust_id
        self._auth_key = auth_key
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._rate_lock = threading.Lock()
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _throttle(self) -> None:
        """공식 문서의 "1초당 1회" 제한을 지켜 계약 정지 등 사고를 예방한다."""
        with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < MIN_REQUEST_INTERVAL_SEC:
                time.sleep(MIN_REQUEST_INTERVAL_SEC - elapsed)
            self._last_request_at = time.monotonic()

    def _post(self, path: str, payload: dict[str, str]) -> list[dict]:
        self._throttle()
        body = {"cust_id": self._cust_id, "auth_key": self._auth_key, **payload}
        response = self._client.post(f"{self._base_url}{path}", data=body)
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            message = data.get("message", {}) or {}
            raise KoscomAPIError(f"KOSCOM API 오류: {message.get('errmsg')} ({message.get('desc')})")
        results = data.get("results")
        if isinstance(results, dict):
            results = [results]
        return results or []

    def get_price(self, symbol: str) -> PriceTick:
        rows = self._post(BASIC_INFO_PATH, {"jcode": symbol, "data_list": "F15001,F15472,F15015"})
        if not rows:
            raise KoscomAPIError(f"{symbol}에 대한 기본정보 응답이 비어 있습니다.")
        row = rows[0]
        price = float(row["F15001"])
        change = float(row.get("F15472", 0) or 0)
        return PriceTick(
            symbol=symbol,
            price=price,
            prev_close=price - change,  # 대비(F15472) 역산 — 문서에 전일종가 필드가 별도로 없음
            volume=int(row.get("F15015", 0) or 0),
            timestamp=datetime.now(),
        )

    def get_orderbook(self, symbol: str) -> OrderBook:
        rows = self._post(HOGA_INFO_PATH, {"jcode": symbol, "data_list": "F14501,F14531,F14511,F14541"})
        if not rows:
            raise KoscomAPIError(f"{symbol}에 대한 호가정보 응답이 비어 있습니다.")
        row = rows[0]
        asks = [OrderBookLevel(price=float(row["F14501"]), qty=int(row["F14511"]))]
        bids = [OrderBookLevel(price=float(row["F14531"]), qty=int(row["F14541"]))]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.now())

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        rows = self._post(
            HIST_INFO_PATH,
            {
                "jcode": symbol,
                "sdate": start.strftime("%Y%m%d"),
                "edate": end.strftime("%Y%m%d"),
                "data_list": "F12506,F15009,F15010,F15011,F15001,F15015",
            },
        )
        return [
            Bar(
                symbol=symbol,
                trade_date=datetime.strptime(str(row["F12506"]), "%Y%m%d").date(),
                open=float(row["F15009"]),
                high=float(row["F15010"]),
                low=float(row["F15011"]),
                close=float(row["F15001"]),
                volume=int(row.get("F15015", 0) or 0),
            )
            for row in rows
        ]
