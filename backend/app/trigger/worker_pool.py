"""워커 풀.

TriggerQueue를 폴링하여 트리거를 하나씩 꺼내 WorkflowEngine으로 실행한다.
PoC는 ThreadPoolExecutor를 사용하며, 노드 실행이 순수 함수/직렬화 가능한 데이터로만
동작하도록 유지하면 추후 ProcessPoolExecutor로도 교체 가능하다.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from app.broker.base import OrderExecutionProvider
from app.dao.base import NodeEventRecord, NodeEventRepository, RunRecord, RunRepository, WorkflowRepository
from app.market_data.base import MarketDataProvider
from app.trigger.queue import Trigger, TriggerQueue
from app.workflow.engine import WorkflowEngine
from app.workflow.events import EventBus
from app.workflow.graph import WorkflowGraph, WorkflowValidationError


class WorkerPool:
    def __init__(
        self,
        trigger_queue: TriggerQueue,
        workflow_repo: WorkflowRepository,
        run_repo: RunRepository,
        node_event_repo: NodeEventRepository,
        event_bus: EventBus,
        market_data: MarketDataProvider,
        broker: OrderExecutionProvider,
        pool_size: int = 4,
        extra_providers: dict[str, Any] | None = None,
    ) -> None:
        self._queue = trigger_queue
        self._workflow_repo = workflow_repo
        self._run_repo = run_repo
        self._node_event_repo = node_event_repo
        self._event_bus = event_bus
        self._market_data = market_data
        self._broker = broker
        self._extra_providers = extra_providers or {}
        self._engine = WorkflowEngine(event_bus)
        self._executor = ThreadPoolExecutor(max_workers=pool_size)
        self._stop_event = threading.Event()
        self._dispatcher_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._dispatcher_thread and self._dispatcher_thread.is_alive():
            return
        self._stop_event.clear()
        self._dispatcher_thread = threading.Thread(target=self._dispatch_loop, name="worker-pool-dispatcher", daemon=True)
        self._dispatcher_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._dispatcher_thread:
            self._dispatcher_thread.join(timeout=5)
        self._executor.shutdown(wait=False)

    def _dispatch_loop(self) -> None:
        while not self._stop_event.is_set():
            trigger = self._queue.get(timeout=0.5)
            if trigger is None:
                continue
            self._executor.submit(self._handle_trigger, trigger)

    def _handle_trigger(self, trigger: Trigger) -> None:
        workflow = self._workflow_repo.get(trigger.workflow_id)
        if workflow is None:
            return

        run_record = RunRecord(
            id=trigger.run_id,
            workflow_id=workflow.id,
            mode="live",
            status="running",
            started_at=datetime.now(),
        )
        self._run_repo.save(run_record)

        try:
            graph = WorkflowGraph.from_dict(workflow.graph)
            result = self._engine.execute(
                workflow_id=workflow.id,
                graph=graph,
                mode="live",
                market_data=self._market_data,
                broker=self._broker,
                run_id=trigger.run_id,
                timestamp=trigger.fired_at,
                extra_providers=self._extra_providers,
            )
            run_record.status = result.status
            run_record.error = result.error
        except WorkflowValidationError as exc:
            run_record.status = "error"
            run_record.error = "; ".join(exc.errors)
        finally:
            run_record.finished_at = datetime.now()
            self._run_repo.save(run_record)
            events = self._event_bus.get_history(trigger.run_id)
            self._node_event_repo.save_many(
                [
                    NodeEventRecord(
                        id=str(uuid.uuid4()),
                        run_id=e.run_id,
                        node_id=e.node_id,
                        node_type=e.node_type,
                        status=e.status,
                        timestamp=e.timestamp,
                        input_json=e.input_snapshot,
                        output_json=e.output_snapshot,
                        error=e.error,
                        duration_ms=e.duration_ms,
                    )
                    for e in events
                ]
            )
