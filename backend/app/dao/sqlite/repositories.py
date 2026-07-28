"""SQLite 기반 Repository 구현체."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.dao.base import (
    AIScoreCacheRecord,
    AIScoreCacheRepository,
    AIUsageRecord,
    AIUsageRepository,
    BacktestResultRecord,
    BacktestResultRepository,
    DisclosureRecord,
    DisclosureRepository,
    IntradayPriceBarRecord,
    IntradayPriceBarRepository,
    NewsRecord,
    NewsRepository,
    NewsSignalRecord,
    NewsSignalRepository,
    NodeEventRecord,
    NodeEventRepository,
    PortfolioRepository,
    PositionRecord,
    PriceBarRecord,
    PriceBarRepository,
    RunRecord,
    RunRepository,
    UserRecord,
    UserRepository,
    WorkflowRecord,
    WorkflowRepository,
)
from app.dao.sqlite.models import (
    AIScoreCacheORM,
    AIUsageORM,
    BacktestResultORM,
    DisclosureORM,
    NewsORM,
    NewsSignalORM,
    NodeEventORM,
    PortfolioCashORM,
    PortfolioPositionORM,
    PriceBarIntradayORM,
    PriceBarORM,
    RunORM,
    UserORM,
    WorkflowORM,
)


class SqliteUserRepository(UserRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def get_by_username(self, username: str) -> UserRecord | None:
        with self._sf() as session:
            row = session.scalar(select(UserORM).where(UserORM.username == username))
            return self._to_record(row) if row else None

    def upsert(self, user: UserRecord) -> None:
        with self._sf() as session:
            row = session.get(UserORM, user.id)
            if row is None:
                row = UserORM(id=user.id, username=user.username, password_hash=user.password_hash, created_at=user.created_at)
                session.add(row)
            else:
                row.username = user.username
                row.password_hash = user.password_hash
            session.commit()

    @staticmethod
    def _to_record(row: UserORM) -> UserRecord:
        return UserRecord(id=row.id, username=row.username, password_hash=row.password_hash, created_at=row.created_at)


class SqliteWorkflowRepository(WorkflowRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        with self._sf() as session:
            row = session.get(WorkflowORM, workflow_id)
            return self._to_record(row) if row else None

    def save(self, workflow: WorkflowRecord) -> None:
        with self._sf() as session:
            row = session.get(WorkflowORM, workflow.id)
            if row is None:
                row = WorkflowORM(id=workflow.id)
                session.add(row)
            row.user_id = workflow.user_id
            row.name = workflow.name
            row.graph_json = workflow.graph
            row.status = workflow.status
            row.schedule_interval_sec = workflow.schedule_interval_sec
            row.created_at = workflow.created_at
            row.updated_at = workflow.updated_at
            session.commit()

    def delete(self, workflow_id: str) -> None:
        with self._sf() as session:
            row = session.get(WorkflowORM, workflow_id)
            if row is not None:
                session.delete(row)
                session.commit()

    def list_by_user(self, user_id: str) -> list[WorkflowRecord]:
        with self._sf() as session:
            rows = session.scalars(select(WorkflowORM).where(WorkflowORM.user_id == user_id)).all()
            return [self._to_record(r) for r in rows]

    def list_active(self) -> list[WorkflowRecord]:
        with self._sf() as session:
            rows = session.scalars(select(WorkflowORM).where(WorkflowORM.status == "active")).all()
            return [self._to_record(r) for r in rows]

    @staticmethod
    def _to_record(row: WorkflowORM) -> WorkflowRecord:
        return WorkflowRecord(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            graph=row.graph_json,
            status=row.status,  # type: ignore[arg-type]
            schedule_interval_sec=row.schedule_interval_sec,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class SqlitePortfolioRepository(PortfolioRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def get_cash(self, user_id: str) -> float | None:
        with self._sf() as session:
            row = session.get(PortfolioCashORM, user_id)
            return row.cash if row else None

    def set_cash(self, user_id: str, cash: float) -> None:
        with self._sf() as session:
            row = session.get(PortfolioCashORM, user_id)
            if row is None:
                row = PortfolioCashORM(user_id=user_id, cash=cash, updated_at=datetime.now())
                session.add(row)
            else:
                row.cash = cash
                row.updated_at = datetime.now()
            session.commit()

    def list_positions(self, user_id: str) -> list[PositionRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(PortfolioPositionORM).where(PortfolioPositionORM.user_id == user_id)
            ).all()
            return [PositionRecord(symbol=r.symbol, qty=r.qty, avg_price=r.avg_price) for r in rows]

    def upsert_position(self, user_id: str, symbol: str, qty: int, avg_price: float) -> None:
        with self._sf() as session:
            row = session.scalar(
                select(PortfolioPositionORM).where(
                    PortfolioPositionORM.user_id == user_id, PortfolioPositionORM.symbol == symbol
                )
            )
            if qty <= 0:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                row = PortfolioPositionORM(id=str(uuid.uuid4()), user_id=user_id, symbol=symbol)
                session.add(row)
            row.qty = qty
            row.avg_price = avg_price
            row.updated_at = datetime.now()
            session.commit()


class SqliteRunRepository(RunRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save(self, run: RunRecord) -> None:
        with self._sf() as session:
            row = session.get(RunORM, run.id)
            if row is None:
                row = RunORM(id=run.id)
                session.add(row)
            row.workflow_id = run.workflow_id
            row.mode = run.mode
            row.status = run.status
            row.started_at = run.started_at
            row.finished_at = run.finished_at
            row.error = run.error
            session.commit()

    def get(self, run_id: str) -> RunRecord | None:
        with self._sf() as session:
            row = session.get(RunORM, run_id)
            return self._to_record(row) if row else None

    def list_by_workflow(self, workflow_id: str) -> list[RunRecord]:
        with self._sf() as session:
            rows = session.scalars(select(RunORM).where(RunORM.workflow_id == workflow_id)).all()
            return [self._to_record(r) for r in rows]

    @staticmethod
    def _to_record(row: RunORM) -> RunRecord:
        return RunRecord(
            id=row.id,
            workflow_id=row.workflow_id,
            mode=row.mode,
            status=row.status,  # type: ignore[arg-type]
            started_at=row.started_at,
            finished_at=row.finished_at,
            error=row.error,
        )


class SqliteNodeEventRepository(NodeEventRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, events: list[NodeEventRecord]) -> None:
        if not events:
            return
        with self._sf() as session:
            for e in events:
                session.add(
                    NodeEventORM(
                        id=e.id,
                        run_id=e.run_id,
                        node_id=e.node_id,
                        node_type=e.node_type,
                        status=e.status,
                        timestamp=e.timestamp,
                        input_json=e.input_json,
                        output_json=e.output_json,
                        error=e.error,
                        duration_ms=e.duration_ms,
                    )
                )
            session.commit()

    def list_by_run(self, run_id: str) -> list[NodeEventRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(NodeEventORM).where(NodeEventORM.run_id == run_id).order_by(NodeEventORM.timestamp)
            ).all()
            return [
                NodeEventRecord(
                    id=r.id,
                    run_id=r.run_id,
                    node_id=r.node_id,
                    node_type=r.node_type,
                    status=r.status,
                    timestamp=r.timestamp,
                    input_json=r.input_json,
                    output_json=r.output_json,
                    error=r.error,
                    duration_ms=r.duration_ms,
                )
                for r in rows
            ]


class SqliteIntradayPriceBarRepository(IntradayPriceBarRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, bars: list[IntradayPriceBarRecord]) -> None:
        if not bars:
            return
        with self._sf() as session:
            for b in bars:
                existing = session.get(PriceBarIntradayORM, (b.symbol, b.bar_datetime, b.interval))
                if existing is None:
                    session.add(
                        PriceBarIntradayORM(
                            symbol=b.symbol,
                            bar_datetime=b.bar_datetime,
                            interval=b.interval,
                            open=b.open,
                            high=b.high,
                            low=b.low,
                            close=b.close,
                            volume=b.volume,
                            source=b.source,
                        )
                    )
                else:
                    existing.open, existing.high, existing.low = b.open, b.high, b.low
                    existing.close, existing.volume, existing.source = b.close, b.volume, b.source
            session.commit()

    def list_range(
        self, symbol: str, start: datetime, end: datetime, interval: str = "minute60"
    ) -> list[IntradayPriceBarRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(PriceBarIntradayORM)
                .where(
                    PriceBarIntradayORM.symbol == symbol,
                    PriceBarIntradayORM.interval == interval,
                    PriceBarIntradayORM.bar_datetime >= start,
                    PriceBarIntradayORM.bar_datetime <= end,
                )
                .order_by(PriceBarIntradayORM.bar_datetime)
            ).all()
            return [
                IntradayPriceBarRecord(
                    symbol=r.symbol,
                    bar_datetime=r.bar_datetime,
                    interval=r.interval,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                    source=r.source,
                )
                for r in rows
            ]


class SqlitePriceBarRepository(PriceBarRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, bars: list[PriceBarRecord]) -> None:
        if not bars:
            return
        with self._sf() as session:
            for b in bars:
                existing = session.get(PriceBarORM, (b.symbol, b.trade_date))
                if existing is None:
                    session.add(
                        PriceBarORM(
                            symbol=b.symbol,
                            trade_date=b.trade_date,
                            open=b.open,
                            high=b.high,
                            low=b.low,
                            close=b.close,
                            volume=b.volume,
                            source=b.source,
                        )
                    )
                else:
                    existing.open, existing.high, existing.low = b.open, b.high, b.low
                    existing.close, existing.volume, existing.source = b.close, b.volume, b.source
            session.commit()

    def list_range(self, symbol: str, start: date, end: date) -> list[PriceBarRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(PriceBarORM)
                .where(PriceBarORM.symbol == symbol, PriceBarORM.trade_date >= start, PriceBarORM.trade_date <= end)
                .order_by(PriceBarORM.trade_date)
            ).all()
            return [
                PriceBarRecord(
                    symbol=r.symbol,
                    trade_date=r.trade_date,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                    source=r.source,
                )
                for r in rows
            ]


class SqliteBacktestResultRepository(BacktestResultRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save(self, result: BacktestResultRecord) -> None:
        with self._sf() as session:
            row = session.get(BacktestResultORM, result.id)
            if row is None:
                row = BacktestResultORM(id=result.id)
                session.add(row)
            row.workflow_id = result.workflow_id
            row.start_date = result.start_date
            row.end_date = result.end_date
            row.initial_capital = result.initial_capital
            row.final_equity = result.final_equity
            row.total_return_pct = result.total_return_pct
            row.cagr_pct = result.cagr_pct
            row.mdd_pct = result.mdd_pct
            row.volatility_pct = result.volatility_pct
            row.win_rate_pct = result.win_rate_pct
            row.profit_loss_ratio = result.profit_loss_ratio
            row.trade_count = result.trade_count
            row.equity_curve_json = result.equity_curve
            row.daily_runs_json = result.daily_runs
            row.universe_json = result.universe
            row.trades_json = result.trades
            row.created_at = result.created_at
            session.commit()

    def get(self, result_id: str) -> BacktestResultRecord | None:
        with self._sf() as session:
            row = session.get(BacktestResultORM, result_id)
            return self._to_record(row) if row else None

    def list_by_workflow(self, workflow_id: str) -> list[BacktestResultRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(BacktestResultORM)
                .where(BacktestResultORM.workflow_id == workflow_id)
                .order_by(BacktestResultORM.created_at.desc())
            ).all()
            return [self._to_record(r) for r in rows]

    def count(self) -> int:
        with self._sf() as session:
            return session.scalar(select(func.count()).select_from(BacktestResultORM)) or 0

    @staticmethod
    def _to_record(row: BacktestResultORM) -> BacktestResultRecord:
        return BacktestResultRecord(
            id=row.id,
            workflow_id=row.workflow_id,
            start_date=row.start_date,
            end_date=row.end_date,
            initial_capital=row.initial_capital,
            final_equity=row.final_equity,
            total_return_pct=row.total_return_pct,
            cagr_pct=row.cagr_pct,
            mdd_pct=row.mdd_pct,
            volatility_pct=row.volatility_pct,
            win_rate_pct=row.win_rate_pct,
            profit_loss_ratio=row.profit_loss_ratio,
            trade_count=row.trade_count,
            equity_curve=row.equity_curve_json,
            daily_runs=row.daily_runs_json or [],
            universe=row.universe_json or [],
            trades=row.trades_json or [],
            created_at=row.created_at,
        )


class SqliteDisclosureRepository(DisclosureRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, items: list[DisclosureRecord]) -> None:
        if not items:
            return
        with self._sf() as session:
            for item in items:
                existing = session.get(DisclosureORM, item.id)
                if existing is None:
                    session.add(
                        DisclosureORM(
                            id=item.id, symbol=item.symbol, corp_name=item.corp_name,
                            report_nm=item.report_nm, rcept_dt=item.rcept_dt, source=item.source,
                        )
                    )
            session.commit()

    def list_recent(self, symbol: str, limit: int = 5) -> list[DisclosureRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(DisclosureORM)
                .where(DisclosureORM.symbol == symbol)
                .order_by(DisclosureORM.rcept_dt.desc())
                .limit(limit)
            ).all()
            return [
                DisclosureRecord(
                    id=r.id, symbol=r.symbol, corp_name=r.corp_name, report_nm=r.report_nm,
                    rcept_dt=r.rcept_dt, source=r.source,
                )
                for r in rows
            ]


class SqliteNewsRepository(NewsRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, items: list[NewsRecord]) -> None:
        if not items:
            return
        with self._sf() as session:
            for item in items:
                existing = session.get(NewsORM, item.id)
                if existing is None:
                    session.add(
                        NewsORM(
                            id=item.id, symbol=item.symbol, title=item.title, body=item.body,
                            published_at=item.published_at, source=item.source,
                        )
                    )
            session.commit()

    def list_recent(self, symbol: str, limit: int = 5) -> list[NewsRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(NewsORM)
                .where(NewsORM.symbol == symbol)
                .order_by(NewsORM.published_at.desc())
                .limit(limit)
            ).all()
            return [
                NewsRecord(
                    id=r.id, symbol=r.symbol, title=r.title, body=r.body,
                    published_at=r.published_at, source=r.source,
                )
                for r in rows
            ]

    def get(self, news_id: str) -> NewsRecord | None:
        with self._sf() as session:
            row = session.get(NewsORM, news_id)
            if row is None:
                return None
            return NewsRecord(
                id=row.id, symbol=row.symbol, title=row.title, body=row.body,
                published_at=row.published_at, source=row.source,
            )

    def list_range(self, symbol: str, start: datetime, end: datetime) -> list[NewsRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(NewsORM)
                .where(NewsORM.symbol == symbol, NewsORM.published_at >= start, NewsORM.published_at <= end)
                .order_by(NewsORM.published_at.asc())
            ).all()
            return [
                NewsRecord(
                    id=r.id, symbol=r.symbol, title=r.title, body=r.body,
                    published_at=r.published_at, source=r.source,
                )
                for r in rows
            ]


class SqliteNewsSignalRepository(NewsSignalRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save_many(self, items: list[NewsSignalRecord]) -> None:
        if not items:
            return
        with self._sf() as session:
            for item in items:
                existing = session.get(NewsSignalORM, item.id)
                if existing is None:
                    session.add(
                        NewsSignalORM(
                            id=item.id, symbol=item.symbol, sector=item.sector,
                            direction=item.direction, event_type=item.event_type, themes=item.themes,
                            base_impact=item.base_impact, sector_score=item.sector_score,
                            domestic_score=item.domestic_score, overseas_score=item.overseas_score,
                            published_at=item.published_at, source=item.source, created_at=item.created_at,
                        )
                    )
            session.commit()

    def list_since(self, cutoff: datetime) -> list[NewsSignalRecord]:
        with self._sf() as session:
            rows = session.scalars(
                select(NewsSignalORM)
                .where(NewsSignalORM.published_at >= cutoff)
                .order_by(NewsSignalORM.published_at.asc())
            ).all()
            return [
                NewsSignalRecord(
                    id=r.id, symbol=r.symbol, sector=r.sector, direction=r.direction,
                    event_type=r.event_type, themes=list(r.themes or []), base_impact=r.base_impact,
                    sector_score=r.sector_score, domestic_score=r.domestic_score,
                    overseas_score=r.overseas_score, published_at=r.published_at,
                    source=r.source, created_at=r.created_at,
                )
                for r in rows
            ]


class SqliteAIScoreCacheRepository(AIScoreCacheRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def get(self, subject_type: str, subject_id: str, prompt_version: str, model: str) -> AIScoreCacheRecord | None:
        with self._sf() as session:
            row = session.scalar(
                select(AIScoreCacheORM).where(
                    AIScoreCacheORM.subject_type == subject_type,
                    AIScoreCacheORM.subject_id == subject_id,
                    AIScoreCacheORM.prompt_version == prompt_version,
                    AIScoreCacheORM.model == model,
                )
            )
            if row is None:
                return None
            return AIScoreCacheRecord(
                id=row.id, subject_type=row.subject_type, subject_id=row.subject_id,
                prompt_version=row.prompt_version, model=row.model, score_json=row.score_json,
                created_at=row.created_at,
            )

    def save(self, record: AIScoreCacheRecord) -> None:
        with self._sf() as session:
            row = session.get(AIScoreCacheORM, record.id)
            if row is None:
                row = AIScoreCacheORM(id=record.id)
                session.add(row)
            row.subject_type = record.subject_type
            row.subject_id = record.subject_id
            row.prompt_version = record.prompt_version
            row.model = record.model
            row.score_json = record.score_json
            row.created_at = record.created_at
            session.commit()


class SqliteAIUsageRepository(AIUsageRepository):
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sf = session_factory

    def save(self, record: AIUsageRecord) -> None:
        with self._sf() as session:
            session.add(
                AIUsageORM(
                    id=record.id,
                    purpose=record.purpose,
                    model=record.model,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    total_tokens=record.total_tokens,
                    created_at=record.created_at,
                )
            )
            session.commit()

    def list_since(self, since: datetime | None) -> list[AIUsageRecord]:
        with self._sf() as session:
            stmt = select(AIUsageORM)
            if since is not None:
                stmt = stmt.where(AIUsageORM.created_at >= since)
            rows = session.scalars(stmt.order_by(AIUsageORM.created_at.asc())).all()
            return [
                AIUsageRecord(
                    id=r.id, purpose=r.purpose, model=r.model,
                    prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens,
                    total_tokens=r.total_tokens, created_at=r.created_at,
                )
                for r in rows
            ]
