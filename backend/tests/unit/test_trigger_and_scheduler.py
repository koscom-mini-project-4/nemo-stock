from __future__ import annotations

from app.dao.base import WorkflowRecord
from app.dao.memory.repositories import InMemoryWorkflowRepository
from app.trigger.queue import InMemoryTriggerQueue, Trigger
from app.trigger.scheduler_service import SchedulerService
from datetime import datetime


def test_trigger_queue_put_get_roundtrip():
    q = InMemoryTriggerQueue()
    assert q.qsize() == 0
    trigger = Trigger(workflow_id="wf1", fired_at=datetime.now())
    q.put(trigger)
    assert q.qsize() == 1
    got = q.get(timeout=1)
    assert got is not None
    assert got.workflow_id == "wf1"
    assert q.get(timeout=0.1) is None


def test_scheduler_fires_immediately_on_first_tick_for_active_workflow():
    repo = InMemoryWorkflowRepository()
    repo.save(
        WorkflowRecord(
            id="wf1", user_id="admin", name="test", graph={"nodes": [], "edges": []},
            status="active", schedule_interval_sec=60,
        )
    )
    q = InMemoryTriggerQueue()
    scheduler = SchedulerService(workflow_repo=repo, trigger_queue=q, tick_seconds=1.0)

    fired = scheduler.tick_once()
    assert fired == 1
    assert q.qsize() == 1

    # 바로 다음 tick에서는 interval이 지나지 않았으므로 재발화되지 않는다.
    fired_again = scheduler.tick_once()
    assert fired_again == 0
    assert q.qsize() == 1


def test_scheduler_ignores_inactive_workflows():
    repo = InMemoryWorkflowRepository()
    repo.save(
        WorkflowRecord(
            id="wf1", user_id="admin", name="test", graph={"nodes": [], "edges": []},
            status="draft", schedule_interval_sec=60,
        )
    )
    q = InMemoryTriggerQueue()
    scheduler = SchedulerService(workflow_repo=repo, trigger_queue=q, tick_seconds=1.0)
    assert scheduler.tick_once() == 0
    assert q.qsize() == 0
