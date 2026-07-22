"""백테스트 시도 시 부족한 시세 데이터를 자동으로 수집해 DB에 저장한다.

`ensure_price_data()`는 요청받은 [start, end] 구간에 해당 종목의 일봉이 하나도
없을 때만 네이버 차트 API(NaverStockChartClient, §0-2)로 수집한다. 이미 데이터가
일부라도 있으면(수동/공공데이터로 적재된 경우 포함) 건드리지 않는다 — 부분 공백
(공휴일 등)까지 정교하게 채우려 하지 않고 "완전히 비어 있을 때만 자동 수집"으로
범위를 좁힌 의도된 단순화다.

시간봉은 부가 데이터로 취급한다: 조회 실패(네트워크 오류, 서버 lookback 한계로
빈 응답 등) 해도 예외를 올리지 않고 조용히 건너뛴다 — 백테스트 엔진 자체는
일봉만으로 동작하므로 시간봉 수집 실패가 백테스트 실행을 막아서는 안 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.dao.base import IntradayPriceBarRepository, PriceBarRepository
from app.data_ingestion.naver_price_client import NaverAPIError, NaverStockChartClient


@dataclass
class AutoIngestResult:
    symbol: str
    daily_fetched: int = 0
    intraday_fetched: int = 0
    skipped_existing: bool = False
    error: str | None = None


def ensure_price_data(
    price_bar_repo: PriceBarRepository,
    intraday_repo: IntradayPriceBarRepository,
    client: NaverStockChartClient,
    symbol: str,
    start: date,
    end: date,
) -> AutoIngestResult:
    existing = price_bar_repo.list_range(symbol, start, end)
    if existing:
        return AutoIngestResult(symbol=symbol, skipped_existing=True)

    try:
        daily_bars = client.fetch_daily_bars(symbol, start, end)
    except NaverAPIError as exc:
        return AutoIngestResult(symbol=symbol, error=str(exc))

    if daily_bars:
        price_bar_repo.save_many(daily_bars)

    intraday_count = 0
    try:
        intraday_bars = client.fetch_hourly_bars(symbol, start, end)
    except NaverAPIError:
        intraday_bars = []
    if intraday_bars:
        intraday_repo.save_many(intraday_bars)
        intraday_count = len(intraday_bars)

    return AutoIngestResult(symbol=symbol, daily_fetched=len(daily_bars), intraday_fetched=intraday_count)
