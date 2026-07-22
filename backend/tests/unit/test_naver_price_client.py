from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest

from app.data_ingestion.naver_price_client import NaverAPIError, NaverStockChartClient


def _make_client(handler) -> NaverStockChartClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return NaverStockChartClient(http_client=http_client)


def test_fetch_daily_bars_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/005930/day")
        return httpx.Response(
            200,
            json=[
                {
                    "localDate": "20260601",
                    "closePrice": 349000.0,
                    "openPrice": 319500.0,
                    "highPrice": 354500.0,
                    "lowPrice": 319500.0,
                    "accumulatedTradingVolume": 45052488,
                    "foreignRetentionRate": 48.3,
                },
                {
                    "localDate": "20260602",
                    "closePrice": 360500.0,
                    "openPrice": 360500.0,
                    "highPrice": 370000.0,
                    "lowPrice": 342000.0,
                    "accumulatedTradingVolume": 44720282,
                    "foreignRetentionRate": 48.07,
                },
            ],
        )

    with _make_client(handler) as client:
        bars = client.fetch_daily_bars("005930", date(2026, 6, 1), date(2026, 6, 2))

    assert len(bars) == 2
    assert bars[0].trade_date == date(2026, 6, 1)
    assert bars[0].close == 349000.0
    assert bars[0].volume == 45052488
    assert bars[1].trade_date == date(2026, 6, 2)


def test_fetch_daily_bars_filters_rows_outside_requested_range():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "localDate": "20260601",
                    "closePrice": 100.0,
                    "openPrice": 100.0,
                    "highPrice": 100.0,
                    "lowPrice": 100.0,
                    "accumulatedTradingVolume": 1,
                },
                {
                    "localDate": "20260705",
                    "closePrice": 200.0,
                    "openPrice": 200.0,
                    "highPrice": 200.0,
                    "lowPrice": 200.0,
                    "accumulatedTradingVolume": 2,
                },
            ],
        )

    with _make_client(handler) as client:
        bars = client.fetch_daily_bars("005930", date(2026, 6, 1), date(2026, 6, 30))

    assert len(bars) == 1
    assert bars[0].trade_date == date(2026, 6, 1)


def test_fetch_daily_bars_empty_for_unknown_symbol():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with _make_client(handler) as client:
        bars = client.fetch_daily_bars("NODATA", date(2026, 6, 1), date(2026, 6, 2))

    assert bars == []


def test_fetch_hourly_bars_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/005930/minute60")
        return httpx.Response(
            200,
            json=[
                {
                    "localDateTime": "20260708090000",
                    "currentPrice": 299000.0,
                    "openPrice": 285500.0,
                    "highPrice": 299500.0,
                    "lowPrice": 283000.0,
                    "accumulatedTradingVolume": 9485425,
                },
                {
                    "localDateTime": "20260708100000",
                    "currentPrice": 287500.0,
                    "openPrice": 299000.0,
                    "highPrice": 300000.0,
                    "lowPrice": 286000.0,
                    "accumulatedTradingVolume": 4500931,
                },
            ],
        )

    with _make_client(handler) as client:
        bars = client.fetch_hourly_bars("005930", date(2026, 7, 8), date(2026, 7, 8))

    assert len(bars) == 2
    assert bars[0].bar_datetime == datetime(2026, 7, 8, 9, 0, 0)
    assert bars[0].interval == "minute60"
    assert bars[0].close == 299000.0
    assert bars[1].bar_datetime == datetime(2026, 7, 8, 10, 0, 0)


def test_fetch_hourly_bars_empty_when_out_of_lookback_range():
    """실측 확인된 한계: 오래된 구간을 요청하면 서버가 빈 리스트를 준다(오류 아님)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    with _make_client(handler) as client:
        bars = client.fetch_hourly_bars("005930", date(2026, 1, 1), date(2026, 1, 7))

    assert bars == []


def test_malformed_response_raises_naver_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with _make_client(handler) as client:
        with pytest.raises(NaverAPIError):
            client.fetch_daily_bars("005930", date(2026, 6, 1), date(2026, 6, 2))
