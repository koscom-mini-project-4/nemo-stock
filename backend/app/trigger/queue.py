"""트리거 큐 인터페이스.

스케줄러가 실행 시각이 도래한 워크플로를 Trigger로 만들어 큐에 넣고,
워커 풀이 큐에서 하나씩 꺼내 실행한다. 이 인터페이스를 구현하면
추후 Redis List/Stream이나 Kafka 기반 큐로 교체할 수 있다.
"""

from __future__ import annotations

import queue as _queue
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trigger:
    workflow_id: str
    fired_at: datetime
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class TriggerQueue(ABC):
    @abstractmethod
    def put(self, trigger: Trigger) -> None: ...

    @abstractmethod
    def get(self, timeout: float | None = None) -> Trigger | None:
        """timeout 내 트리거가 없으면 None을 반환한다(블로킹 폴링)."""

    @abstractmethod
    def qsize(self) -> int: ...


class InMemoryTriggerQueue(TriggerQueue):
    """queue.Queue 기반 PoC 구현. 프로세스 내에서만 유효하다."""

    def __init__(self) -> None:
        self._q: _queue.Queue[Trigger] = _queue.Queue()

    def put(self, trigger: Trigger) -> None:
        self._q.put(trigger)

    def get(self, timeout: float | None = None) -> Trigger | None:
        try:
            return self._q.get(timeout=timeout)
        except _queue.Empty:
            return None

    def qsize(self) -> int:
        return self._q.qsize()
