"""공공데이터포털 금융위원회_주식시세정보 API 클라이언트.

엔드포인트: GetStockSecuritiesInfoService/getStockPriceInfo (종목코드+기간 기준 일별 시세)
서비스키는 data.go.kr에서 발급받아 backend/.env의 DATA_GO_KR_SERVICE_KEY로 설정한다.
데이터는 영업일 기준 일 1회(T+1) 갱신되므로 실시간용이 아니라 백테스트용 일봉 소스로 사용한다.

참고: https://www.data.go.kr/data/15094808/openapi.do
"""

from __future__ import annotations

from datetime import date, datetime

import httpx

from app.dao.base import PriceBarRecord

DEFAULT_BASE_URL = "http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"


class PublicDataAPIError(RuntimeError):
    pass


class PublicDataPriceClient:
    def __init__(
        self,
        service_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._service_key = service_key
        self._base_url = base_url
        self._timeout = timeout
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PublicDataPriceClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_daily_prices(self, symbol: str, start: date, end: date, num_of_rows: int = 500) -> list[PriceBarRecord]:
        """종목코드(6자리) 기준 [start, end] 구간의 일별 시세를 모두 가져온다(페이지네이션 자동 처리)."""
        bars: list[PriceBarRecord] = []
        page_no = 1
        while True:
            params = {
                "serviceKey": self._service_key,
                "resultType": "json",
                "srtnCd": symbol,
                "beginBasDt": start.strftime("%Y%m%d"),
                "endBasDt": end.strftime("%Y%m%d"),
                "numOfRows": num_of_rows,
                "pageNo": page_no,
            }
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
            body = self._parse_body(response)
            rows = self._extract_items(body)
            bars.extend(self._to_bar(symbol, row) for row in rows)

            total_count = int(body.get("totalCount", 0) or 0)
            if not rows or page_no * num_of_rows >= total_count:
                break
            page_no += 1
        return bars

    @staticmethod
    def _parse_body(response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise PublicDataAPIError(f"응답을 JSON으로 파싱할 수 없습니다: {response.text[:200]}") from exc

        header = data.get("response", {}).get("header", {})
        result_code = header.get("resultCode")
        if result_code not in (None, "00", "0"):
            raise PublicDataAPIError(f"공공데이터 API 오류: {header.get('resultMsg', result_code)}")
        return data.get("response", {}).get("body", {})

    @staticmethod
    def _extract_items(body: dict) -> list[dict]:
        items = body.get("items")
        if not items:
            return []
        rows = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(rows, dict):
            rows = [rows]
        return rows or []

    @staticmethod
    def _to_bar(symbol: str, row: dict) -> PriceBarRecord:
        return PriceBarRecord(
            symbol=symbol,
            trade_date=datetime.strptime(row["basDt"], "%Y%m%d").date(),
            open=float(row["mkp"]),
            high=float(row["hipr"]),
            low=float(row["lopr"]),
            close=float(row["clpr"]),
            volume=int(row["trqu"]),
            source="data.go.kr",
        )
