"""스케줄러 서비스.

1초 tick마다 status=active인 워크플로를 순회하며 next_fire_time이 도래하면
Trigger를 큐에 push한다. 백그라운드 스레드로 실행되며, app/batch/worker.py에서
API 프로세스와 별도로도 기동할 수 있도록 순수 로직만 담는다.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from app.dao.base import WorkflowRepository
from app.trigger.queue import Trigger, TriggerQueue


class SchedulerService:
    def __init__(
        self,
        workflow_repo: WorkflowRepository,
        trigger_queue: TriggerQueue,
        tick_seconds: float = 1.0,
    ) -> None:
        self._workflow_repo = workflow_repo
        self._queue = trigger_queue
        self._tick_seconds = tick_seconds
        self._next_fire: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="scheduler-service", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick_once()
            self._stop_event.wait(self._tick_seconds)

    def tick_once(self) -> int:
        """활성 워크플로 중 실행 시각이 도래한 것을 큐에 넣는다. 넣은 개수를 반환(테스트용)."""
        now = time.monotonic()
        fired = 0
        for workflow in self._workflow_repo.list_active():
            due_at = self._next_fire.get(workflow.id)
            if due_at is None:
                self._next_fire[workflow.id] = now  # 최초 활성화 시 즉시 실행
                due_at = now
            if now >= due_at:
                self._queue.put(Trigger(workflow_id=workflow.id, fired_at=datetime.now()))
                interval = max(workflow.schedule_interval_sec, 1)
                self._next_fire[workflow.id] = now + interval
                fired += 1
        return fired

    def forget(self, workflow_id: str) -> None:
        self._next_fire.pop(workflow_id, None)
