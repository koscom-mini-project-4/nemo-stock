from __future__ import annotations

from datetime import date, timedelta

from app.broker.base import OrderRequest
from app.broker.dummy import DummyOrderExecutionProvider
from app.market_data.dummy import DummyMarketDataProvider


def test_market_data_deterministic_with_seed():
    p1 = DummyMarketDataProvider(seed_prices={"005930": 70000}, seed=123)
    p2 = DummyMarketDataProvider(seed_prices={"005930": 70000}, seed=123)
    assert p1.get_price("005930").price == p2.get_price("005930").price


def test_market_data_ohlcv_length():
    provider = DummyMarketDataProvider(seed=7)
    end = date.today()
    start = end - timedelta(days=4)
    bars = provider.get_ohlcv("005930", start, end)
    assert len(bars) == 5
    assert all(b.high >= b.low for b in bars)


def test_broker_buy_then_sell_roundtrip():
    broker = DummyOrderExecutionProvider(initial_cash=1_000_000)
    buy = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=10, ref_price=1000)
    )
    assert buy.status == "filled"
    assert broker.get_balance().cash == 990_000
    positions = broker.get_positions()
    assert positions[0].qty == 10

    sell = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="sell", order_type="market", qty=10, ref_price=1100)
    )
    assert sell.status == "filled"
    assert broker.get_positions() == []
    assert broker.get_balance().cash == 990_000 + 11_000


def test_broker_rejects_insufficient_cash():
    broker = DummyOrderExecutionProvider(initial_cash=100)
    result = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=10, ref_price=1000)
    )
    assert result.status == "rejected"
    assert result.reason == "잔고 부족"


def test_broker_rejects_oversell():
    broker = DummyOrderExecutionProvider(initial_cash=1_000_000)
    result = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="sell", order_type="market", qty=5, ref_price=1000)
    )
    assert result.status == "rejected"
    assert result.reason == "보유 수량 부족"
