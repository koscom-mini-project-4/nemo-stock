from __future__ import annotations

from app.broker.base import OrderRequest
from app.broker.persistent_dummy import PersistentOrderExecutionProvider
from app.dao.memory.repositories import InMemoryPortfolioRepository


def test_persistent_broker_seeds_default_cash_once():
    repo = InMemoryPortfolioRepository()
    PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=5_000_000.0)
    assert repo.get_cash("admin") == 5_000_000.0

    # 이미 시드된 계정을 새 인스턴스로 다시 열어도 기존 현금을 덮어쓰지 않는다.
    repo.set_cash("admin", 4_000_000.0)
    PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=5_000_000.0)
    assert repo.get_cash("admin") == 4_000_000.0


def test_persistent_broker_buy_then_sell_roundtrip():
    repo = InMemoryPortfolioRepository()
    broker = PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=1_000_000.0)

    buy = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=10, ref_price=1000)
    )
    assert buy.status == "filled"
    assert broker.get_balance().cash == 990_000
    assert broker.get_positions()[0].qty == 10

    sell = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="sell", order_type="market", qty=10, ref_price=1100)
    )
    assert sell.status == "filled"
    assert broker.get_positions() == []
    assert broker.get_balance().cash == 990_000 + 11_000


def test_persistent_broker_rejects_insufficient_cash_and_oversell():
    repo = InMemoryPortfolioRepository()
    broker = PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=100.0)

    result = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=10, ref_price=1000)
    )
    assert result.status == "rejected"
    assert result.reason == "잔고 부족"

    result = broker.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="sell", order_type="market", qty=5, ref_price=1000)
    )
    assert result.status == "rejected"
    assert result.reason == "보유 수량 부족"


def test_persistent_broker_state_survives_new_instance_same_repo():
    """서버 재시작 시뮬레이션: 같은 repo(=같은 DB)로 새 provider 인스턴스를 만들어도
    이전 체결 결과(현금/보유수량)가 그대로 유지되어야 한다."""
    repo = InMemoryPortfolioRepository()
    broker1 = PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=1_000_000.0)
    broker1.place_order(
        OrderRequest(run_id="r1", symbol="005930", side="buy", order_type="market", qty=10, ref_price=1000)
    )

    broker2 = PersistentOrderExecutionProvider(repo, "admin", default_initial_cash=1_000_000.0)
    assert broker2.get_balance().cash == 990_000
    positions = broker2.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "005930"
    assert positions[0].qty == 10
