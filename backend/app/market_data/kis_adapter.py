"""한국투자증권(KIS) Open API 기반 시세 어댑터.

엔드포인트/필드명은 공식 GitHub(github.com/koreainvestment/open-trading-api)의 실제
동작하는 예제 코드(examples_llm/domestic_stock/{inquire_price,inquire_daily_itemchartprice,
inquire_asking_price_exp_ccn})를 직접 대조해 확인했다. 시세 조회 계열 tr_id(F로 시작)는
모의/실전 구분 없이 동일값을 쓴다(app/broker/kis_auth.py::to_paper_tr_id 참조 — 이 tr_id들은
치환 대상이 아니다). 실제 앱키 발급 전이라 실호출 검증은 못했다.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from app.broker.kis_auth import KISOAuthTokenProvider
from app.market_data.base import Bar, MarketDataProvider, OrderBook, OrderBookLevel, PriceTick

PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
ASKING_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
DAILY_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

TR_PRICE = "FHKST01010100"
TR_ASKING_PRICE = "FHKST01010200"
TR_DAILY_CHART = "FHKST03010100"

MARKET_DIV_KRX = "J"  # 조건 시장 분류 코드: J=KRX, NX=NXT, UN=통합


class KISMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str,
        is_paper: bool = True,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not app_key or not app_secret:
            raise ValueError(
                "KISMarketDataProvider 사용에는 KIS_APP_KEY/KIS_APP_SECRET 설정이 필요합니다."
            )
        self._base_url = base_url.rstrip("/")
        self._is_paper = is_paper
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._auth = KISOAuthTokenProvider(app_key, app_secret, base_url, http_client=self._client)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _get(self, path: str, tr_id: str, params: dict) -> dict:
        response = self._client.get(
            f"{self._base_url}{path}", params=params, headers=self._auth.auth_headers(tr_id, self._is_paper)
        )
        response.raise_for_status()
        return response.json()

    def get_price(self, symbol: str) -> PriceTick:
        data = self._get(
            PRICE_PATH, TR_PRICE, {"FID_COND_MRKT_DIV_CODE": MARKET_DIV_KRX, "FID_INPUT_ISCD": symbol}
        )
        output = data.get("output", {})
        price = float(output.get("stck_prpr", 0) or 0)
        # 전일종가 = 현재가 - 전일대비(prdy_vrss). inquire-price 응답에는 전일종가가 직접
        # 필드로 없어(원본 예제 확인 결과) 역산한다 — Toss 어댑터에는 없던 KIS 고유 계산.
        change = float(output.get("prdy_vrss", 0) or 0)
        return PriceTick(
            symbol=symbol,
            price=price,
            prev_close=price - change,
            volume=int(output.get("acml_vol", 0) or 0),
            timestamp=datetime.now(),
        )

    def get_orderbook(self, symbol: str) -> OrderBook:
        data = self._get(
            ASKING_PRICE_PATH,
            TR_ASKING_PRICE,
            {"FID_COND_MRKT_DIV_CODE": MARKET_DIV_KRX, "FID_INPUT_ISCD": symbol},
        )
        output = data.get("output1", {})  # 호가정보(단일 객체). output2는 예상체결정보(미사용)
        asks = [OrderBookLevel(price=float(output.get("askp1", 0) or 0), qty=int(output.get("askp_rsqn1", 0) or 0))]
        bids = [OrderBookLevel(price=float(output.get("bidp1", 0) or 0), qty=int(output.get("bidp_rsqn1", 0) or 0))]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=datetime.now())

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        data = self._get(
            DAILY_CHART_PATH,
            TR_DAILY_CHART,
            {
                "FID_COND_MRKT_DIV_CODE": MARKET_DIV_KRX,
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": end.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",  # 0=수정주가, 1=원주가 (원본 예제 docstring 기준)
            },
        )
        rows = data.get("output2", [])  # output1은 종목 요약(단일 객체), output2가 일자별 배열
        return [
            Bar(
                symbol=symbol,
                trade_date=datetime.strptime(row["stck_bsop_date"], "%Y%m%d").date(),
                open=float(row["stck_oprc"]),
                high=float(row["stck_hgpr"]),
                low=float(row["stck_lwpr"]),
                close=float(row["stck_clpr"]),
                volume=int(row.get("acml_vol", 0) or 0),
            )
            for row in rows
        ]
