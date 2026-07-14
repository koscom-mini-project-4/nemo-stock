from __future__ import annotations

import uuid
from datetime import datetime

from app.dao.base import NodeEventRecord, RunRecord, UserRecord, WorkflowRecord
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteNodeEventRepository,
    SqliteRunRepository,
    SqliteUserRepository,
    SqliteWorkflowRepository,
)


def _session_factory(tmp_path):
    db_path = tmp_path / f"{uuid.uuid4().hex}.db"
    engine = make_engine(f"sqlite:///{db_path}")
    init_db(engine)
    return make_session_factory(engine)


def test_user_repository_roundtrip(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteUserRepository(sf)
    repo.upsert(UserRecord(id="u1", username="admin", password_hash="hash"))
    fetched = repo.get_by_username("admin")
    assert fetched is not None
    assert fetched.id == "u1"


def test_workflow_repository_crud(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteWorkflowRepository(sf)
    wf = WorkflowRecord(
        id="wf1", user_id="admin", name="test", graph={"nodes": [], "edges": []}, status="draft",
        schedule_interval_sec=30,
    )
    repo.save(wf)
    fetched = repo.get("wf1")
    assert fetched is not None
    assert fetched.name == "test"

    fetched.status = "active"
    repo.save(fetched)
    assert repo.list_active()[0].id == "wf1"

    repo.delete("wf1")
    assert repo.get("wf1") is None


def test_run_and_node_event_repository(tmp_path):
    sf = _session_factory(tmp_path)
    run_repo = SqliteRunRepository(sf)
    event_repo = SqliteNodeEventRepository(sf)

    run = RunRecord(id="r1", workflow_id="wf1", mode="test", status="running", started_at=datetime.now())
    run_repo.save(run)
    assert run_repo.get("r1").status == "running"

    event_repo.save_many(
        [
            NodeEventRecord(
                id="e1", run_id="r1", node_id="n1", node_type="scheduler.interval",
                status="success", timestamp=datetime.now(),
            )
        ]
    )
    events = event_repo.list_by_run("r1")
    assert len(events) == 1
    assert events[0].node_id == "n1"
