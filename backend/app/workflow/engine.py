"""워크플로 실행 엔진.

위상 정렬된 순서대로 노드를 실행하며, 노드별 실행 이벤트를 EventBus로 발행한다.
live/test/backtest 실행이 동일한 execute()를 사용하고, Provider(market_data/broker)와
overrides(테스트용 임의 값 주입)만 호출부에서 다르게 넘긴다.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.broker.base import OrderExecutionProvider
from app.market_data.base import MarketDataProvider
from app.nodes.base import NODE_REGISTRY, NodeContext, RunMode, create_node
from app.workflow.events import EventBus, NodeExecutionEvent
from app.workflow.graph import WorkflowGraph, WorkflowValidationError


@dataclass
class RunResult:
    run_id: str
    workflow_id: str
    mode: RunMode
    status: str  # "success" | "error"
    started_at: datetime
    finished_at: datetime
    node_contexts: dict[str, NodeContext] = field(default_factory=dict)
    error: str | None = None

    @property
    def final_context(self) -> NodeContext | None:
        if not self.node_contexts:
            return None
        # 위상 정렬 마지막 노드의 컨텍스트(실행 순서 보존을 위해 호출부에서 order 전달받아 구성)
        return list(self.node_contexts.values())[-1]


class WorkflowEngine:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    def execute(
        self,
        workflow_id: str,
        graph: WorkflowGraph,
        mode: RunMode,
        market_data: MarketDataProvider,
        broker: OrderExecutionProvider,
        overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
        run_id: str | None = None,
        timestamp: datetime | None = None,
        extra_providers: dict[str, Any] | None = None,
        target_node_id: str | None = None,
    ) -> RunResult:
        """extra_providers: ai_client/news_repo/disclosure_repo/ai_score_cache_repo 등
        market_data/broker 외에 노드가 필요로 하는 추가 의존성을 node.execute(**providers)로 전달한다.

        target_node_id: 지정하면 그 노드와 조상 노드만 실행한다(노드 단독 테스트, §0-9) —
        나머지 그래프는 건드리지 않고 위상 순서만 그 부분집합으로 좁힌다.
        """
        run_id = run_id or str(uuid.uuid4())
        started_at = datetime.now()
        timestamp = timestamp or started_at
        overrides = overrides or {}
        extra_providers = extra_providers or {}

        errors = graph.validate()
        if errors:
            raise WorkflowValidationError(errors)

        order = graph.topological_order()
        if target_node_id is not None:
            if target_node_id not in graph.nodes:
                raise WorkflowValidationError([f"존재하지 않는 노드입니다: {target_node_id}"])
            scope = graph.ancestors_of(target_node_id)
            order = [n for n in order if n in scope]
        ctx_by_node: dict[str, NodeContext] = {}
        root_context = NodeContext(run_id=run_id, mode=mode, timestamp=timestamp)

        # 런 시작 시점의 계좌 스냅샷(1회 조회) — 이 런 자신의 주문이 실행 도중 이 값을
        # 바꾸지 않도록 고정한다. scheduler 노드가 아니라 여기서 채우므로 새 노드 타입 없이
        # 모든 워크플로에 held_qty/held_avg_price/cash/equity가 자동으로 제공된다.
        balance = broker.get_balance()
        positions_by_symbol = {p.symbol: p for p in broker.get_positions()}

        def _apply_portfolio_fields(ctx: NodeContext) -> None:
            for symbol, data in ctx.symbols.items():
                if "held_qty" in data:
                    continue
                position = positions_by_symbol.get(symbol)
                data["held_qty"] = position.qty if position else 0
                data["held_avg_price"] = position.avg_price if position else 0.0
                data["cash"] = balance.cash
                data["equity"] = balance.equity
            ctx.meta.setdefault("cash", balance.cash)
            ctx.meta.setdefault("equity", balance.equity)

        try:
            for node_id in order:
                node_def = graph.get_node(node_id)
                node = create_node(node_def.type, node_id, node_def.params)

                preds = graph.predecessors(node_id)
                if preds:
                    merged = ctx_by_node[preds[0]]
                    for p in preds[1:]:
                        merged = merged.merged_with(ctx_by_node[p])
                    input_ctx = merged.clone()
                else:
                    input_ctx = root_context.clone()

                self._event_bus.publish(
                    NodeExecutionEvent(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_def.type,
                        status="running",
                        input_snapshot=input_ctx.snapshot(),
                    )
                )

                start = time.perf_counter()
                try:
                    node_overrides = overrides.get(node_id)
                    if node_overrides:
                        output_ctx = input_ctx.clone()
                        for symbol, values in node_overrides.items():
                            output_ctx.symbols.setdefault(symbol, {}).update(values)
                    else:
                        output_ctx = node.execute(
                            input_ctx, market_data=market_data, broker=broker, **extra_providers
                        )
                    _apply_portfolio_fields(output_ctx)
                    duration_ms = (time.perf_counter() - start) * 1000
                    ctx_by_node[node_id] = output_ctx
                    self._event_bus.publish(
                        NodeExecutionEvent(
                            run_id=run_id,
                            node_id=node_id,
                            node_type=node_def.type,
                            status="success",
                            output_snapshot=output_ctx.snapshot(),
                            duration_ms=duration_ms,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    duration_ms = (time.perf_counter() - start) * 1000
                    self._event_bus.publish(
                        NodeExecutionEvent(
                            run_id=run_id,
                            node_id=node_id,
                            node_type=node_def.type,
                            status="error",
                            error=str(exc),
                            duration_ms=duration_ms,
                        )
                    )
                    raise

            finished_at = datetime.now()
            ordered_contexts = {nid: ctx_by_node[nid] for nid in order}
            return RunResult(
                run_id=run_id,
                workflow_id=workflow_id,
                mode=mode,
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                node_contexts=ordered_contexts,
            )
        except Exception as exc:  # noqa: BLE001
            finished_at = datetime.now()
            return RunResult(
                run_id=run_id,
                workflow_id=workflow_id,
                mode=mode,
                status="error",
                started_at=started_at,
                finished_at=finished_at,
                node_contexts=ctx_by_node,
                error=str(exc),
            )
        finally:
            self._event_bus.close_run(run_id)


__all__ = ["WorkflowEngine", "RunResult", "NODE_REGISTRY"]
