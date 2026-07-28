"""백테스트 시도 시 부족한 시세 데이터를 자동으로 수집해 DB에 저장한다.

`ensure_price_data()`는 요청받은 [start, end] 구간에 해당 종목의 데이터가 없거나,
있어도 가장 최신 날짜가 end로부터 STALE_THRESHOLD_DAYS일 이상 오래됐으면 네이버
차트 API(NaverStockChartClient, §0-2)로 [start, end] 전체를 다시 수집한다
(PriceBarRepository.save_many가 upsert이므로 기존 행은 덮어쓰고 새 날짜만 추가되어
안전하다). 예전에는 "구간에 데이터가 조금이라도 있으면 건너뜀"이었으나, 이 경우
과거 세션에서 짧게(예: 6/10~7/1) 수집된 데이터가 이후 요청(예: 오늘까지 백테스트)의
최신 데이터 갱신을 영구히 막아버려 백테스트/차트가 실제로는 존재하지 않는 옛 날짜
까지만 나오는 문제가 있었다 — 실사용 중 발견되어 "최신 데이터가 있는지"까지 확인하는
쪽으로 완화했다.

시간봉은 부가 데이터로 취급한다: 조회 실패(네트워크 오류, 서버 lookback 한계로
빈 응답 등) 해도 예외를 올리지 않고 조용히 건너뛴다 — 백테스트 엔진 자체는
일봉만으로 동작하므로 시간봉 수집 실패가 백테스트 실행을 막아서는 안 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.dao.base import IntradayPriceBarRepository, PriceBarRepository
from app.data_ingestion.naver_price_client import NaverAPIError, NaverStockChartClient

# 이 이상 최신 데이터가 없으면 "구간에 데이터가 있다"고 보지 않고 재수집한다.
# 주말/연휴로 며칠 비는 경우를 정상으로 봐주기 위한 여유(영업일 기준이 아니라 달력일 기준).
STALE_THRESHOLD_DAYS = 5


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
        latest = max(b.trade_date for b in existing)
        if (end - latest).days < STALE_THRESHOLD_DAYS:
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
