"""네이버 증권 차트 API 클라이언트 (일봉 + 시간봉).

공공데이터포털/KOSCOM CHECK-API는 모두 일봉만 제공하므로(§0-2 결정 사항 참고),
장중 시간봉(시간 단위 캔들)을 확보할 별도 소스가 필요하다. `stock.naver.com`이
프론트엔드에서 사용하는 비공식 공개 엔드포인트(`api.stock.naver.com/chart/...`)는
별도 인증/키 없이 호출 가능하며, 일봉/시간봉 모두 제공한다(2026-07-22 실측 확인).

엔드포인트: https://api.stock.naver.com/chart/domestic/item/{symbol}/{chart_type}
  - chart_type="day": 일봉. start~end 전체 구간을 그대로 반환(기간 제한 확인 안 됨).
  - chart_type="minute60": 시간봉(60분). **중요한 실측 한계**: startDateTime을 과거로
    넉넉히 잡아도 서버가 실제로는 최근 영업일 기준 제한된 lookback(실측 약 8거래일치,
    56봉)만 반환한다. 오래된 과거 시간봉은 이 소스로 확보할 수 없다 — 백테스트는
    여전히 일봉(days) 기준으로 동작하며, 시간봉은 "가능한 범위까지 저장"하는 부가
    데이터로 취급한다.

존재하지 않는 종목코드를 조회해도 오류가 아니라 빈 리스트(HTTP 200)를 반환한다.
비공식 API이므로 향후 응답 형식이 바뀌면 이 클라이언트만 교체하면 되도록 인터페이스를
공공데이터 클라이언트와 동일한 모양(fetch_daily_bars 등)으로 맞춘다.
"""

from __future__ import annotations

from datetime import date, datetime, time

import httpx

from app.dao.base import IntradayPriceBarRecord, PriceBarRecord

DEFAULT_BASE_URL = "https://api.stock.naver.com/chart/domestic/item"

_HEADERS = {
    "accept": "*/*",
    "origin": "https://stock.naver.com",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
}


class NaverAPIError(RuntimeError):
    pass


class NaverStockChartClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "NaverStockChartClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_daily_bars(self, symbol: str, start: date, end: date) -> list[PriceBarRecord]:
        """[start, end] 구간의 일봉을 가져온다. 데이터가 없으면 빈 리스트."""
        rows = self._get(symbol, "day", start, end)
        bars: list[PriceBarRecord] = []
        for row in rows:
            try:
                trade_date = datetime.strptime(row["localDate"], "%Y%m%d").date()
            except (KeyError, ValueError) as exc:
                raise NaverAPIError(f"일봉 응답 형식이 예상과 다릅니다: {row}") from exc
            if not (start <= trade_date <= end):
                continue
            bars.append(
                PriceBarRecord(
                    symbol=symbol,
                    trade_date=trade_date,
                    open=float(row["openPrice"]),
                    high=float(row["highPrice"]),
                    low=float(row["lowPrice"]),
                    close=float(row["closePrice"]),
                    volume=int(row["accumulatedTradingVolume"]),
                    source="naver",
                )
            )
        return bars

    def fetch_hourly_bars(self, symbol: str, start: date, end: date) -> list[IntradayPriceBarRecord]:
        """[start, end] 구간의 시간봉(60분)을 가져온다.

        서버가 실제로 지원하는 lookback보다 이전 구간을 요청하면 빈 리스트가 올 수 있다
        (오류 아님 — 오래된 시간봉은 이 소스로 확보 불가하다는 뜻).
        """
        rows = self._get(symbol, "minute60", start, end)
        bars: list[IntradayPriceBarRecord] = []
        for row in rows:
            try:
                bar_dt = datetime.strptime(row["localDateTime"], "%Y%m%d%H%M%S")
            except (KeyError, ValueError) as exc:
                raise NaverAPIError(f"시간봉 응답 형식이 예상과 다릅니다: {row}") from exc
            if not (start <= bar_dt.date() <= end):
                continue
            bars.append(
                IntradayPriceBarRecord(
                    symbol=symbol,
                    bar_datetime=bar_dt,
                    interval="minute60",
                    open=float(row["openPrice"]),
                    high=float(row["highPrice"]),
                    low=float(row["lowPrice"]),
                    close=float(row["currentPrice"]),
                    volume=int(row["accumulatedTradingVolume"]),
                    source="naver",
                )
            )
        return bars

    def _get(self, symbol: str, chart_type: str, start: date, end: date) -> list[dict]:
        url = f"{self._base_url}/{symbol}/{chart_type}"
        params = {
            "startDateTime": datetime.combine(start, time.min).strftime("%Y%m%d%H%M"),
            "endDateTime": datetime.combine(end, time.max).strftime("%Y%m%d%H%M"),
        }
        headers = {**_HEADERS, "referer": f"https://stock.naver.com/domestic/stock/{symbol}/price"}
        response = self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise NaverAPIError(f"응답을 JSON으로 파싱할 수 없습니다: {response.text[:200]}") from exc
        if not isinstance(data, list):
            raise NaverAPIError(f"예상치 못한 응답 형식(리스트 아님): {data!r}"[:200])
        return data
