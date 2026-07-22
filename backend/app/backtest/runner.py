"""백테스트 러너.

과거 일봉을 날짜순으로 리플레이하며 WorkflowEngine.execute(mode="backtest")를
그대로 재사용한다(라이브/테스트와 동일한 실행 경로). MarketDataProvider는
HistoricalMarketDataProvider, OrderExecutionProvider는 DummyOrderExecutionProvider(페이퍼)로 고정한다.

거래일마다 별도의 run_id로 실행하고 WorkerPool(app/trigger/worker_pool.py)과 동일한 방식으로
RunRecord/NodeEventRecord를 저장한다 — 백테스트 결과 화면에서 특정 날짜를 골라 그날의 노드
그래프 실행을 "테스트 실행"과 동일한 디버그 패널로 재생할 수 있게 하기 위함(DESIGN.md §8).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from app.backtest.metrics import BacktestMetrics, compute_metrics
from app.broker.base import OrderResult
from app.broker.dummy import DummyOrderExecutionProvider
from app.dao.base import NodeEventRepository, PriceBarRepository, RunRecord, RunRepository
from app.market_data.historical import HistoricalMarketDataProvider
from app.workflow.engine import WorkflowEngine
from app.workflow.events import EventBus
from app.workflow.graph import WorkflowGraph
from app.workflow.run_persistence import events_to_records


@dataclass
class BacktestResult:
    workflow_id: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    metrics: BacktestMetrics
    equity_curve: list[tuple[date, float]] = field(default_factory=list)
    orders: list[OrderResult] = field(default_factory=list)
    trading_days: int = 0
    daily_runs: list[tuple[date, str]] = field(default_factory=list)


class BacktestRunner:
    def __init__(
        self,
        engine: WorkflowEngine,
        price_bar_repo: PriceBarRepository,
        run_repo: RunRepository,
        node_event_repo: NodeEventRepository,
        event_bus: EventBus,
    ):
        self._engine = engine
        self._price_bar_repo = price_bar_repo
        self._run_repo = run_repo
        self._node_event_repo = node_event_repo
        self._event_bus = event_bus

    def run(
        self,
        workflow_id: str,
        graph: WorkflowGraph,
        universe: list[str],
        start: date,
        end: date,
        initial_capital: float = 10_000_000.0,
        extra_providers: dict[str, Any] | None = None,
    ) -> BacktestResult:
        if not universe:
            raise ValueError("백테스트 대상 종목(universe)이 비어 있습니다.")

        trading_days = self._trading_calendar(universe, start, end)
        if not trading_days:
            raise ValueError(
                "해당 기간에 대한 시세 데이터가 없습니다. 먼저 /data/ingest/prices로 데이터를 적재하세요."
            )

        market_data = HistoricalMarketDataProvider(self._price_bar_repo, universe)
        broker = DummyOrderExecutionProvider(initial_cash=initial_capital)

        equity_curve: list[tuple[date, float]] = []
        daily_runs: list[tuple[date, str]] = []
        for day in trading_days:
            market_data.advance_to(day)
            run_id = str(uuid.uuid4())
            result = self._engine.execute(
                workflow_id=workflow_id,
                graph=graph,
                mode="backtest",
                market_data=market_data,
                broker=broker,
                run_id=run_id,
                timestamp=datetime.combine(day, time()),
                extra_providers=extra_providers,
            )
            self._save_run(run_id, workflow_id, result.status, result.error)
            daily_runs.append((day, run_id))
            if result.status != "success":
                continue
            equity_curve.append((day, self._mark_to_market_equity(broker, market_data, universe)))

        metrics = compute_metrics(equity_curve, broker.orders, initial_capital)
        final_equity = equity_curve[-1][1] if equity_curve else initial_capital

        return BacktestResult(
            workflow_id=workflow_id,
            start_date=start,
            end_date=end,
            initial_capital=initial_capital,
            final_equity=final_equity,
            metrics=metrics,
            equity_curve=equity_curve,
            orders=list(broker.orders),
            trading_days=len(trading_days),
            daily_runs=daily_runs,
        )

    def _save_run(self, run_id: str, workflow_id: str, status: str, error: str | None) -> None:
        now = datetime.now()
        self._run_repo.save(
            RunRecord(
                id=run_id, workflow_id=workflow_id, mode="backtest", status=status,
                started_at=now, finished_at=now, error=error,
            )
        )
        self._node_event_repo.save_many(events_to_records(self._event_bus, run_id))

    def _trading_calendar(self, universe: list[str], start: date, end: date) -> list[date]:
        dates: set[date] = set()
        for symbol in universe:
            bars = self._price_bar_repo.list_range(symbol, start, end)
            dates.update(b.trade_date for b in bars)
        return sorted(dates)

    @staticmethod
    def _mark_to_market_equity(
        broker: DummyOrderExecutionProvider, market_data: HistoricalMarketDataProvider, universe: list[str]
    ) -> float:
        equity = broker.get_balance().cash
        for pos in broker.get_positions():
            if pos.symbol not in universe:
                continue
            try:
                price = market_data.get_price(pos.symbol).price
            except RuntimeError:
                price = pos.avg_price
            equity += pos.qty * price
        return equity
