from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text

from app.dao.base import BacktestResultRecord, IntradayPriceBarRecord, NodeEventRecord, RunRecord, UserRecord, WorkflowRecord
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteBacktestResultRepository,
    SqliteIntradayPriceBarRepository,
    SqliteNodeEventRepository,
    SqlitePortfolioRepository,
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


def test_portfolio_repository_cash_and_positions_roundtrip(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqlitePortfolioRepository(sf)

    assert repo.get_cash("admin") is None
    repo.set_cash("admin", 10_000_000.0)
    assert repo.get_cash("admin") == 10_000_000.0

    repo.set_cash("admin", 9_300_000.0)
    assert repo.get_cash("admin") == 9_300_000.0

    assert repo.list_positions("admin") == []
    repo.upsert_position("admin", "005930", 10, 70000.0)
    positions = repo.list_positions("admin")
    assert len(positions) == 1
    assert positions[0].symbol == "005930"
    assert positions[0].qty == 10

    repo.upsert_position("admin", "005930", 15, 71000.0)
    positions = repo.list_positions("admin")
    assert len(positions) == 1
    assert positions[0].qty == 15
    assert positions[0].avg_price == 71000.0

    # 다른 계정 데이터와 섞이지 않아야 한다.
    repo.upsert_position("other", "000660", 5, 120000.0)
    assert len(repo.list_positions("admin")) == 1
    assert len(repo.list_positions("other")) == 1

    # qty<=0이면 삭제된다.
    repo.upsert_position("admin", "005930", 0, 0.0)
    assert repo.list_positions("admin") == []


def test_init_db_adds_missing_column_to_preexisting_table(tmp_path):
    """create_all()은 없는 테이블만 만들 뿐 기존 테이블에 새 컬럼(예: daily_runs_json)을
    추가해주지 않는다 — init_db()가 ALTER TABLE로 이를 보정하는지 확인한다(기존 로컬 DB
    호환성 회귀 방지)."""
    db_path = tmp_path / f"{uuid.uuid4().hex}.db"
    engine = make_engine(f"sqlite:///{db_path}")
    # daily_runs_json 컬럼이 없는 "구버전" backtest_results 테이블을 흉내낸다.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE backtest_results (
                    id VARCHAR(64) PRIMARY KEY,
                    workflow_id VARCHAR(64),
                    start_date DATE,
                    end_date DATE,
                    initial_capital FLOAT,
                    final_equity FLOAT,
                    total_return_pct FLOAT,
                    cagr_pct FLOAT,
                    mdd_pct FLOAT,
                    volatility_pct FLOAT,
                    win_rate_pct FLOAT,
                    profit_loss_ratio FLOAT,
                    trade_count INTEGER,
                    equity_curve_json JSON,
                    created_at DATETIME
                )
                """
            )
        )

    init_db(engine)  # 컬럼 보정이 여기서 일어나야 한다.
    sf = make_session_factory(engine)
    repo = SqliteBacktestResultRepository(sf)
    record = BacktestResultRecord(
        id="bt1", workflow_id="wf1", start_date=datetime(2026, 6, 1).date(), end_date=datetime(2026, 6, 2).date(),
        initial_capital=1_000_000.0, final_equity=1_050_000.0, total_return_pct=5.0, cagr_pct=5.0, mdd_pct=0.0,
        volatility_pct=1.0, win_rate_pct=100.0, profit_loss_ratio=None, trade_count=1,
        equity_curve=[{"date": "2026-06-01", "equity": 1_000_000.0}],
        daily_runs=[{"date": "2026-06-01", "run_id": "r1"}],
    )
    repo.save(record)
    fetched = repo.get("bt1")
    assert fetched is not None
    assert fetched.daily_runs == [{"date": "2026-06-01", "run_id": "r1"}]
