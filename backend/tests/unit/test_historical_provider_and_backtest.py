from __future__ import annotations

from datetime import date, timedelta

from app.backtest.runner import BacktestRunner
from app.dao.base import PriceBarRecord
from app.dao.memory.repositories import InMemoryNodeEventRepository, InMemoryPriceBarRepository, InMemoryRunRepository
from app.market_data.historical import HistoricalMarketDataProvider
from app.nodes import load_all_nodes
from app.workflow.engine import WorkflowEngine
from app.workflow.events import InMemoryEventBus
from app.workflow.graph import WorkflowGraph

load_all_nodes()


def _seed_uptrend(repo: InMemoryPriceBarRepository, symbol: str, start: date, days: int, start_price: float) -> None:
    """일정하게 우상향하는 합성 가격 시계열을 만든다(결정적 백테스트 결과를 위해)."""
    price = start_price
    bars = []
    for i in range(days):
        d = start + timedelta(days=i)
        open_ = price
        close = price * 1.01  # 매일 1% 상승
        bars.append(
            PriceBarRecord(
                symbol=symbol, trade_date=d, open=open_, high=close, low=open_, close=close, volume=10000,
            )
        )
        price = close
    repo.save_many(bars)


def _buy_on_uptrend_graph() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 1, "universe": "TESTSYM"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > prev_close"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
        ],
    }


def test_historical_provider_replays_bars_up_to_advance_date():
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=10, start_price=100.0)

    provider = HistoricalMarketDataProvider(repo, universe=["TESTSYM"])
    provider.advance_to(start + timedelta(days=4))
    tick = provider.get_price("TESTSYM")
    # 5번째 거래일(index 4)까지의 데이터만 보여야 한다.
    assert tick.price > 100.0
    bars = provider.get_ohlcv("TESTSYM", start, start + timedelta(days=4))
    assert len(bars) == 5


def test_backtest_runner_on_synthetic_uptrend_produces_positive_return():
    repo = InMemoryPriceBarRepository()
    start = date(2025, 1, 1)
    _seed_uptrend(repo, "TESTSYM", start, days=20, start_price=100.0)

    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    run_repo = InMemoryRunRepository()
    node_event_repo = InMemoryNodeEventRepository()
    runner = BacktestRunner(engine, repo, run_repo, node_event_repo, bus)

    result = runner.run(
        workflow_id="wf1",
        graph=graph,
        universe=["TESTSYM"],
        start=start,
        end=start + timedelta(days=19),
        initial_capital=1_000_000.0,
    )

    assert result.trading_days == 20
    assert len(result.equity_curve) == 20
    # 매일 상승하는 종목을 계속 사들이므로 최종 자산이 초기 자본보다 커야 한다.
    assert result.final_equity > result.initial_capital
    assert result.metrics.total_return_pct > 0
    assert result.metrics.mdd_pct == 0.0  # 우상향만 하므로 낙폭이 없어야 한다

    # 거래일마다 별도 run_id로 RunRecord/NodeEventRecord가 저장되어야 한다(일자별 그래프 재생용).
    assert len(result.daily_runs) == 20
    for day, run_id in result.daily_runs:
        assert run_repo.get(run_id) is not None
        assert run_repo.get(run_id).mode == "backtest"
        assert len(node_event_repo.list_by_run(run_id)) > 0

    # 매일 상승하는 합성 시세라 조건이 매일 통과 -> 매수도 매일 체결되며, OrderResult.filled_at은
    # 실제 벽시계 시각이므로 러너가 시뮬레이션 날짜를 직접 태깅해야 한다.
    assert result.universe == ["TESTSYM"]
    assert len(result.trades) == 20
    daily_run_ids = {run_id for _, run_id in result.daily_runs}
    for day, run_id, order in result.trades:
        assert order.symbol == "TESTSYM"
        assert order.side == "buy"
        assert order.status == "filled"
        assert run_id in daily_run_ids
    assert {d for d, _, _ in result.trades} == {d for d, _ in result.daily_runs}


def test_backtest_runner_raises_when_no_price_data():
    repo = InMemoryPriceBarRepository()
    graph = WorkflowGraph.from_dict(_buy_on_uptrend_graph())
    bus = InMemoryEventBus()
    engine = WorkflowEngine(bus)
    runner = BacktestRunner(engine, repo, InMemoryRunRepository(), InMemoryNodeEventRepository(), bus)

    import pytest

    with pytest.raises(ValueError):
        runner.run(
            workflow_id="wf1",
            graph=graph,
            universe=["TESTSYM"],
            start=date(2025, 1, 1),
            end=date(2025, 1, 10),
        )
