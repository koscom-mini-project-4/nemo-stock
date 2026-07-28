"""execution.market_order 노드의 수량 결정 로직(target_qty > 비율(%) > 고정수량) 테스트."""

from __future__ import annotations

from datetime import datetime

from app.broker.dummy import DummyOrderExecutionProvider
from app.nodes.base import NodeContext, create_node


def _run(params: dict, symbols: dict) -> NodeContext:
    node = create_node("execution.market_order", "n1", params)
    ctx = NodeContext(run_id="r1", mode="test", timestamp=datetime(2026, 7, 28), symbols=symbols)
    broker = DummyOrderExecutionProvider(initial_cash=100_000_000)
    return node.execute(ctx, broker=broker)


def test_default_qty_mode_uses_fixed_qty_for_backward_compat():
    out = _run({"side": "buy", "qty": 3}, {"005930": {"price": 70000}})
    assert out.meta["orders"][0]["qty"] == 3


def test_target_qty_takes_priority_over_percent_mode():
    out = _run(
        {"side": "buy", "qty_mode": "가능수량 비율(%)", "qty_pct": 50},
        {"005930": {"price": 70000, "target_qty": 7, "cash": 100_000_000}},
    )
    assert out.meta["orders"][0]["qty"] == 7


def test_percent_mode_buy_uses_cash_over_price():
    out = _run(
        {"side": "buy", "qty_mode": "가능수량 비율(%)", "qty_pct": 50},
        {"005930": {"price": 70000, "cash": 1_400_000}},
    )
    # 1,400,000 / 70,000 * 0.5 = 10
    assert out.meta["orders"][0]["qty"] == 10


def test_percent_mode_sell_uses_held_qty():
    out = _run(
        {"side": "sell", "qty_mode": "가능수량 비율(%)", "qty_pct": 50},
        {"005930": {"price": 70000, "held_qty": 20}},
    )
    assert out.meta["orders"][0]["qty"] == 10


def test_percent_mode_zero_qty_is_skipped():
    out = _run(
        {"side": "buy", "qty_mode": "가능수량 비율(%)", "qty_pct": 50},
        {"005930": {"price": 70000, "cash": 0}},
    )
    assert out.meta.get("orders", []) == []
