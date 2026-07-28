from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text

from app.dao.base import (
    AIUsageRecord,
    BacktestResultRecord,
    IntradayPriceBarRecord,
    NewsRecord,
    NewsSignalRecord,
    NodeEventRecord,
    RunRecord,
    UserRecord,
    WorkflowRecord,
)
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteAIUsageRepository,
    SqliteBacktestResultRepository,
    SqliteIntradayPriceBarRepository,
    SqliteNewsRepository,
    SqliteNewsSignalRepository,
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
        universe=["005930"],
        trades=[{"date": "2026-06-01", "run_id": "r1", "order_id": "o1", "symbol": "005930", "side": "buy",
                 "qty": 1, "price": 70000.0, "status": "filled", "reason": None, "realized_pnl": None}],
    )
    repo.save(record)
    fetched = repo.get("bt1")
    assert fetched is not None
    assert fetched.daily_runs == [{"date": "2026-06-01", "run_id": "r1"}]
    assert fetched.universe == ["005930"]
    assert fetched.trades[0]["order_id"] == "o1"


def test_news_repository_get_and_list_range(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteNewsRepository(sf)

    repo.save_many(
        [
            NewsRecord(id="n1", symbol="005930", title="제목1", body="본문1", published_at=datetime(2026, 6, 1, 9, 0)),
            NewsRecord(id="n2", symbol="005930", title="제목2", body="본문2", published_at=datetime(2026, 6, 3, 9, 0)),
            NewsRecord(id="n3", symbol="000660", title="제목3", body="본문3", published_at=datetime(2026, 6, 2, 9, 0)),
        ]
    )

    assert repo.get("n1").title == "제목1"
    assert repo.get("nope") is None

    ranged = repo.list_range("005930", datetime(2026, 6, 1), datetime(2026, 6, 2))
    assert [n.id for n in ranged] == ["n1"]

    ranged_full = repo.list_range("005930", datetime(2026, 6, 1), datetime(2026, 6, 30))
    assert [n.id for n in ranged_full] == ["n1", "n2"]


def test_backtest_result_repository_count(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteBacktestResultRepository(sf)
    assert repo.count() == 0

    for i in range(3):
        repo.save(
            BacktestResultRecord(
                id=f"bt{i}", workflow_id="wf1", start_date=datetime(2026, 6, 1).date(),
                end_date=datetime(2026, 6, 2).date(), initial_capital=1_000_000.0, final_equity=1_050_000.0,
                total_return_pct=5.0, cagr_pct=5.0, mdd_pct=0.0, volatility_pct=1.0, win_rate_pct=100.0,
                profit_loss_ratio=None, trade_count=1, equity_curve=[], daily_runs=[], universe=["005930"], trades=[],
            )
        )
    assert repo.count() == 3


def test_ai_usage_repository_save_and_list_since(tmp_path):
    sf = _session_factory(tmp_path)
    repo = SqliteAIUsageRepository(sf)

    repo.save(
        AIUsageRecord(
            id="u1", purpose="workflow_draft", model="gpt-5.6-luna",
            prompt_tokens=100, completion_tokens=20, total_tokens=120, created_at=datetime(2026, 6, 1),
        )
    )
    repo.save(
        AIUsageRecord(
            id="u2", purpose="newsstock_classify", model="gpt-4o-mini",
            prompt_tokens=50, completion_tokens=10, total_tokens=60, created_at=datetime(2026, 6, 3),
        )
    )

    all_records = repo.list_since(None)
    assert [r.id for r in all_records] == ["u1", "u2"]

    since_records = repo.list_since(datetime(2026, 6, 2))
    assert [r.id for r in since_records] == ["u2"]


def test_news_signal_repository_roundtrip_preserves_title(tmp_path):
    """§0-9: title 필드가 sqlite 저장/조회를 거쳐도 보존되는지(뉴스신호 근거 표시용)."""
    sf = _session_factory(tmp_path)
    repo = SqliteNewsSignalRepository(sf)

    repo.save_many(
        [
            NewsSignalRecord(
                id="s1", symbol="005930", sector="반도체", direction=1, event_type="Earnings_Contract",
                themes=["HBM"], base_impact=0.8, sector_score=0.5, domestic_score=0.2, overseas_score=0.0,
                published_at=datetime(2026, 6, 1), source="manual", title="삼성전자 HBM 대규모 수주",
            ),
            NewsSignalRecord(
                id="s2", symbol=None, sector="반도체", direction=-1, event_type="Macro_Indicator",
                themes=[], base_impact=-0.3, sector_score=-0.2, domestic_score=-0.1, overseas_score=0.0,
                published_at=datetime(2026, 6, 2), source="manual", title=None,
            ),
        ]
    )

    records = repo.list_since(datetime(2026, 5, 1))
    by_id = {r.id: r for r in records}
    assert by_id["s1"].title == "삼성전자 HBM 대규모 수주"
    assert by_id["s2"].title is None
