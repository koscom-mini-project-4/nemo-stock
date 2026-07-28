from __future__ import annotations

from datetime import date, datetime

from app.dao.base import IntradayPriceBarRecord, PriceBarRecord
from app.dao.memory.repositories import InMemoryIntradayPriceBarRepository, InMemoryPriceBarRepository
from app.data_ingestion.auto_ingest import ensure_price_data
from app.data_ingestion.naver_price_client import NaverAPIError


class _FakeClient:
    def __init__(self, daily=None, hourly=None, daily_error=None):
        self.daily = daily or []
        self.hourly = hourly or []
        self.daily_error = daily_error
        self.daily_calls = 0
        self.hourly_calls = 0

    def fetch_daily_bars(self, symbol, start, end):
        self.daily_calls += 1
        if self.daily_error:
            raise self.daily_error
        return self.daily

    def fetch_hourly_bars(self, symbol, start, end):
        self.hourly_calls += 1
        return self.hourly


def test_ensure_price_data_skips_when_latest_data_is_fresh():
    """최신 데이터가 end 근처(STALE_THRESHOLD_DAYS 이내)까지 있으면 재수집하지 않는다."""
    price_repo = InMemoryPriceBarRepository()
    intraday_repo = InMemoryIntradayPriceBarRepository()
    price_repo.save_many(
        [PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 8), open=1, high=1, low=1, close=1, volume=1)]
    )
    client = _FakeClient(daily=[PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 9), open=2, high=2, low=2, close=2, volume=2)])

    result = ensure_price_data(price_repo, intraday_repo, client, "005930", date(2026, 6, 1), date(2026, 6, 10))

    assert result.skipped_existing is True
    assert client.daily_calls == 0
    assert client.hourly_calls == 0


def test_ensure_price_data_refetches_when_existing_data_is_stale():
    """데이터가 있어도 가장 최신 날짜가 end에서 STALE_THRESHOLD_DAYS일 이상 떨어져 있으면
    (예: 과거 세션에서 짧은 기간만 수집된 채 방치) 다시 수집해 최신 날짜까지 채운다."""
    price_repo = InMemoryPriceBarRepository()
    intraday_repo = InMemoryIntradayPriceBarRepository()
    price_repo.save_many(
        [PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 1), open=1, high=1, low=1, close=1, volume=1)]
    )
    fresh_bar = PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 10), open=2, high=2, low=2, close=2, volume=2)
    client = _FakeClient(daily=[fresh_bar])

    result = ensure_price_data(price_repo, intraday_repo, client, "005930", date(2026, 6, 1), date(2026, 6, 10))

    assert result.skipped_existing is False
    assert result.daily_fetched == 1
    assert client.daily_calls == 1
    assert price_repo.list_range("005930", date(2026, 6, 10), date(2026, 6, 10)) == [fresh_bar]


def test_ensure_price_data_fetches_daily_and_hourly_when_missing():
    price_repo = InMemoryPriceBarRepository()
    intraday_repo = InMemoryIntradayPriceBarRepository()
    daily = [PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 1), open=1, high=1, low=1, close=1, volume=1)]
    hourly = [
        IntradayPriceBarRecord(
            symbol="005930",
            bar_datetime=datetime(2026, 6, 1, 9),
            interval="minute60",
            open=1,
            high=1,
            low=1,
            close=1,
            volume=1,
        )
    ]
    client = _FakeClient(daily=daily, hourly=hourly)

    result = ensure_price_data(price_repo, intraday_repo, client, "005930", date(2026, 6, 1), date(2026, 6, 10))

    assert result.skipped_existing is False
    assert result.daily_fetched == 1
    assert result.intraday_fetched == 1
    assert price_repo.list_range("005930", date(2026, 6, 1), date(2026, 6, 10)) == daily
    assert len(intraday_repo.list_range("005930", datetime(2026, 6, 1), datetime(2026, 6, 10, 23, 59))) == 1


def test_ensure_price_data_returns_error_without_raising_on_daily_failure():
    price_repo = InMemoryPriceBarRepository()
    intraday_repo = InMemoryIntradayPriceBarRepository()
    client = _FakeClient(daily_error=NaverAPIError("boom"))

    result = ensure_price_data(price_repo, intraday_repo, client, "005930", date(2026, 6, 1), date(2026, 6, 10))

    assert result.error == "boom"
    assert result.daily_fetched == 0


def test_ensure_price_data_ignores_hourly_failure_when_daily_succeeds():
    price_repo = InMemoryPriceBarRepository()
    intraday_repo = InMemoryIntradayPriceBarRepository()
    daily = [PriceBarRecord(symbol="005930", trade_date=date(2026, 6, 1), open=1, high=1, low=1, close=1, volume=1)]

    class _HourlyFailsClient(_FakeClient):
        def fetch_hourly_bars(self, symbol, start, end):
            raise NaverAPIError("no intraday")

    client = _HourlyFailsClient(daily=daily)

    result = ensure_price_data(price_repo, intraday_repo, client, "005930", date(2026, 6, 1), date(2026, 6, 10))

    assert result.daily_fetched == 1
    assert result.intraday_fetched == 0
    assert result.error is None
