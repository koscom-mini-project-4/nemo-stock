"""노드 실행 이벤트 + EventBus 인터페이스.

WS /ws/runs/{run_id}가 EventBus.subscribe(run_id)를 소비하여 프론트로 push하고,
프론트는 이를 받아 실행 중인 노드를 하이라이트(깜빡임)하고 입출력을 디버그 패널에 표시한다.
"""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator, Literal

NodeEventStatus = Literal["running", "success", "error", "skipped"]


@dataclass
class NodeExecutionEvent:
    run_id: str
    node_id: str
    node_type: str
    status: NodeEventStatus
    timestamp: datetime = field(default_factory=datetime.now)
    input_snapshot: dict[str, Any] | None = None
    output_snapshot: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "timestamp": self.timestamp.isoformat(),
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# 스트림 종료를 알리는 sentinel
_SENTINEL = object()


class EventBus(ABC):
    @abstractmethod
    def publish(self, event: NodeExecutionEvent) -> None: ...

    @abstractmethod
    def close_run(self, run_id: str) -> None:
        """해당 run의 이벤트 스트림 종료를 구독자에게 알린다."""

    @abstractmethod
    def subscribe(self, run_id: str) -> Iterator[NodeExecutionEvent]: ...

    @abstractmethod
    def get_history(self, run_id: str) -> list[NodeExecutionEvent]: ...


class InMemoryEventBus(EventBus):
    """queue.Queue 기반 PoC 구현. 프로세스 내 pub/sub만 지원.
    추후 Redis pub/sub 등으로 교체 시 동일 인터페이스를 구현하면 된다.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, list[queue.Queue]] = {}
        self._history: dict[str, list[NodeExecutionEvent]] = {}

    def publish(self, event: NodeExecutionEvent) -> None:
        with self._lock:
            self._history.setdefault(event.run_id, []).append(event)
            subscribers = list(self._queues.get(event.run_id, []))
        for q in subscribers:
            q.put(event)

    def close_run(self, run_id: str) -> None:
        with self._lock:
            subscribers = list(self._queues.get(run_id, []))
        for q in subscribers:
            q.put(_SENTINEL)

    def subscribe(self, run_id: str) -> Iterator[NodeExecutionEvent]:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._queues.setdefault(run_id, []).append(q)
            for past_event in self._history.get(run_id, []):
                q.put(past_event)
        try:
            while True:
                item = q.get()
                if item is _SENTINEL:
                    return
                yield item
        finally:
            with self._lock:
                subs = self._queues.get(run_id, [])
                if q in subs:
                    subs.remove(q)

    def get_history(self, run_id: str) -> list[NodeExecutionEvent]:
        with self._lock:
            return list(self._history.get(run_id, []))
