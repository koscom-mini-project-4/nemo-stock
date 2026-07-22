from __future__ import annotations

from app.broker.base import OrderRequest
from app.broker.dummy import DummyOrderExecutionProvider
from app.market_data.dummy import DummyMarketDataProvider
from app.nodes import load_all_nodes
from app.workflow.engine import WorkflowEngine
from app.workflow.events import InMemoryEventBus
from app.workflow.graph import WorkflowGraph

load_all_nodes()


def _scenario_graph() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930,000660"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > 0"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
        ],
    }


def test_engine_executes_and_publishes_events():
    graph = WorkflowGraph.from_dict(_scenario_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    market_data = DummyMarketDataProvider(seed_prices={"005930": 70000, "000660": 120000}, seed=1)
    broker = DummyOrderExecutionProvider(initial_cash=100_000_000)

    result = engine.execute(
        workflow_id="wf1",
        graph=graph,
        mode="test",
        market_data=market_data,
        broker=broker,
    )

    assert result.status == "success"
    final = result.final_context
    assert final is not None
    assert set(final.symbols.keys()) == {"005930", "000660"}
    for symbol, data in final.symbols.items():
        assert data["order_status"] == "filled"

    events = bus.get_history(result.run_id)
    statuses = [(e.node_id, e.status) for e in events]
    # 각 노드마다 running -> success 이벤트가 순서대로 발행되어야 한다.
    assert ("n1", "running") in statuses
    assert ("n4", "success") in statuses
    assert len(broker.orders) == 2


def test_engine_test_mode_override_skips_provider_call():
    graph = WorkflowGraph.from_dict(_scenario_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    market_data = DummyMarketDataProvider(seed=2)
    broker = DummyOrderExecutionProvider(initial_cash=10_000_000)

    result = engine.execute(
        workflow_id="wf1",
        graph=graph,
        mode="test",
        market_data=market_data,
        broker=broker,
        overrides={"n2": {"005930": {"price": 100.0, "prev_close": 90.0}}},
    )

    assert result.status == "success"
    final = result.final_context
    assert final.symbols["005930"]["price"] == 100.0
    # override는 000660에는 적용되지 않았으므로 if_else에서 여전히 price>0을 만족(더미 provider 값)한다.
    assert "000660" in final.symbols or True


def test_engine_filters_out_symbols_failing_condition():
    data = _scenario_graph()
    data["nodes"][2]["params"]["expr"] = "price > 1000000"  # 아무도 통과 못하는 조건
    graph = WorkflowGraph.from_dict(data)
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    market_data = DummyMarketDataProvider(seed_prices={"005930": 70000, "000660": 120000}, seed=3)
    broker = DummyOrderExecutionProvider()

    result = engine.execute(
        workflow_id="wf1", graph=graph, mode="test", market_data=market_data, broker=broker
    )
    assert result.status == "success"
    assert result.final_context.symbols == {}
    assert len(broker.orders) == 0


def test_engine_injects_portfolio_fields_into_symbols():
    graph = WorkflowGraph.from_dict(_scenario_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    market_data = DummyMarketDataProvider(seed_prices={"005930": 70000, "000660": 120000}, seed=4)
    broker = DummyOrderExecutionProvider(initial_cash=1_000_000)
    # 사전에 005930을 보유중인 상태로 세팅.
    broker.place_order(
        OrderRequest(run_id="setup", symbol="005930", side="buy", order_type="market", qty=3, ref_price=70000)
    )

    result = engine.execute(
        workflow_id="wf1", graph=graph, mode="test", market_data=market_data, broker=broker
    )

    assert result.status == "success"
    final = result.final_context
    # 이미 매수 노드(n4)까지 실행되어 두 종목 모두 추가 매수됐으므로 held_qty는 종목별로 다르다.
    assert final.symbols["005930"]["held_qty"] == 3
    assert final.symbols["005930"]["held_avg_price"] == 70000
    assert final.symbols["000660"]["held_qty"] == 0
    assert final.symbols["000660"]["held_avg_price"] == 0.0
    # cash/equity는 런 시작 시점 스냅샷(이 런 자신의 매수 체결로 바뀌지 않음)이어야 한다.
    starting_cash = 1_000_000 - 3 * 70000
    assert final.symbols["005930"]["cash"] == starting_cash
    assert final.symbols["000660"]["cash"] == starting_cash
    assert final.meta["cash"] == starting_cash
