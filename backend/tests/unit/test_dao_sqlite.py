from __future__ import annotations

import uuid
from datetime import datetime

from app.dao.base import IntradayPriceBarRecord, NodeEventRecord, RunRecord, UserRecord, WorkflowRecord
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteIntradayPriceBarRepository,
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


def test_intraday_price_bar_repository_roundtrip_and_upsert(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteIntradayPriceBarRepository(sf)

    bar = IntradayPriceBarRecord(
        symbol="005930",
        bar_datetime=datetime(2026, 7, 8, 9, 0, 0),
        interval="minute60",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=1000,
        source="naver",
    )
    repo.save_many([bar])

    rows = repo.list_range("005930", datetime(2026, 7, 8, 0, 0), datetime(2026, 7, 8, 23, 59))
    assert len(rows) == 1
    assert rows[0].close == 1.5

    updated = IntradayPriceBarRecord(
        symbol="005930",
        bar_datetime=datetime(2026, 7, 8, 9, 0, 0),
        interval="minute60",
        open=1.0,
        high=2.0,
        low=0.5,
        close=9.9,
        volume=2000,
        source="naver",
    )
    repo.save_many([updated])
    rows = repo.list_range("005930", datetime(2026, 7, 8, 0, 0), datetime(2026, 7, 8, 23, 59))
    assert len(rows) == 1
    assert rows[0].close == 9.9

    other_interval = repo.list_range("005930", datetime(2026, 7, 8, 0, 0), datetime(2026, 7, 8, 23, 59), interval="day")
    assert other_interval == []
