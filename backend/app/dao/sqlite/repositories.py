"""SQLite 기반 Repository 구현체."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.dao.base import (
    NodeEventRecord,
    NodeEventRepository,
    PriceBarRecord,
    PriceBarRepository,
    RunRecord,
    RunRepository,
    UserRecord,
    UserRepository,
    WorkflowRecord,
    WorkflowRepository,
)
from app.dao.sqlite.models import NodeEventORM, PriceBarORM, RunORM, UserORM, WorkflowORM


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
