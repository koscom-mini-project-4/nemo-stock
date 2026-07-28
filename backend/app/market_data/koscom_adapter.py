"""KOSCOM CHECK-API 기반 실시세 어댑터.

CHECK-API는 코스콤 "CHECK 단말" 구독 고객에게 발급되는 cust_id/auth_key가 있어야 호출 가능한
유료 서비스다. 2026-07-15 실제 발급받은 자격증명으로 get_price/get_orderbook/get_ohlcv
(basic_info/hoga_info/hist_info) 3개 엔드포인트 모두 실제 호출까지 검증 완료했다
(삼성전자/SK하이닉스 실시세·호가·일별시세 정상 조회 확인). 엔드포인트/필드명 조사 근거와
원문은 docs/koscom-api/README.md, docs/koscom-api/pages/(전체 사이트 크롤 결과)에 보관되어 있다.

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

# 종목코드/한글명 코드 마스터(§0-10 심볼 마스터 동기화 폴백 소스). jcode 없이 시장 그룹 전체를
# 한 번에 돌려주는 벌크 엔드포인트라(docs/koscom-api/pages/01-stock-api/거래소 종목/01-코드
# 정보.md, 코스닥 종목/01-코드 정보.md) 시장당 호출 1회로 전 종목을 가져올 수 있다 — 공공데이터
# 포털(DATA_GO_KR_SERVICE_KEY)이 서비스 미승인으로 빈 응답만 주는 문제(2026-07-28 실사용 중
# 발견)의 대안으로 쓴다.
CODE_INFO_PATHS: dict[str, str] = {
    "KOSPI": "/stock/m001/code_info",
    "KOSDAQ": "/stock/m003/code_info",
}

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

    def fetch_symbol_master(self) -> list[dict]:
        """거래소(KOSPI)/코스닥(KOSDAQ) 전 종목의 코드/한글종목명을 가져온다(§0-10).

        code_info는 jcode 없이 부르면 시장 그룹 전체를 한 번에 돌려주는 벌크 엔드포인트라
        시장당 호출 1회(총 2회)로 끝난다 — 초당 1회 제한(_throttle)에 걸려도 약 1초만 더
        걸린다. 반환: [{"symbol", "name", "market"}, ...].
        """
        out: list[dict] = []
        for market, path in CODE_INFO_PATHS.items():
            rows = self._post(path, {"data_list": "F16013,F16002"})
            for row in rows:
                symbol = str(row.get("F16013") or "").strip()
                name = str(row.get("F16002") or "").strip()
                if not symbol or not name:
                    continue
                out.append({"symbol": symbol, "name": name, "market": market})
        return out

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
