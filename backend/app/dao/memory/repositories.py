"""인메모리 Repository 구현체 (휘발성 테스트 실행/유닛테스트용).

SQLite 구현체와 동일한 ABC를 구현하므로 서비스 계층 코드는 변경 없이 교체 가능하다.
"""

from __future__ import annotations

from datetime import date, datetime

from app.dao.base import (
    AIScoreCacheRecord,
    AIScoreCacheRepository,
    DisclosureRecord,
    DisclosureRepository,
    IntradayPriceBarRecord,
    IntradayPriceBarRepository,
    NewsRecord,
    NewsRepository,
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


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, UserRecord] = {}

    def get_by_username(self, username: str) -> UserRecord | None:
        return next((u for u in self._by_id.values() if u.username == username), None)

    def upsert(self, user: UserRecord) -> None:
        self._by_id[user.id] = user


class InMemoryWorkflowRepository(WorkflowRepository):
    def __init__(self) -> None:
        self._store: dict[str, WorkflowRecord] = {}

    def get(self, workflow_id: str) -> WorkflowRecord | None:
        return self._store.get(workflow_id)

    def save(self, workflow: WorkflowRecord) -> None:
        self._store[workflow.id] = workflow

    def delete(self, workflow_id: str) -> None:
        self._store.pop(workflow_id, None)

    def list_by_user(self, user_id: str) -> list[WorkflowRecord]:
        return [w for w in self._store.values() if w.user_id == user_id]

    def list_active(self) -> list[WorkflowRecord]:
        return [w for w in self._store.values() if w.status == "active"]


class InMemoryRunRepository(RunRepository):
    def __init__(self) -> None:
        self._store: dict[str, RunRecord] = {}

    def save(self, run: RunRecord) -> None:
        self._store[run.id] = run

    def get(self, run_id: str) -> RunRecord | None:
        return self._store.get(run_id)

    def list_by_workflow(self, workflow_id: str) -> list[RunRecord]:
        return [r for r in self._store.values() if r.workflow_id == workflow_id]


class InMemoryNodeEventRepository(NodeEventRepository):
    def __init__(self) -> None:
        self._store: dict[str, list[NodeEventRecord]] = {}

    def save_many(self, events: list[NodeEventRecord]) -> None:
        for e in events:
            self._store.setdefault(e.run_id, []).append(e)

    def list_by_run(self, run_id: str) -> list[NodeEventRecord]:
        return list(self._store.get(run_id, []))


class InMemoryPriceBarRepository(PriceBarRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, date], PriceBarRecord] = {}

    def save_many(self, bars: list[PriceBarRecord]) -> None:
        for b in bars:
            self._store[(b.symbol, b.trade_date)] = b

    def list_range(self, symbol: str, start: date, end: date) -> list[PriceBarRecord]:
        return sorted(
            (b for (s, d), b in self._store.items() if s == symbol and start <= d <= end),
            key=lambda b: b.trade_date,
        )


class InMemoryIntradayPriceBarRepository(IntradayPriceBarRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, datetime, str], IntradayPriceBarRecord] = {}

    def save_many(self, bars: list[IntradayPriceBarRecord]) -> None:
        for b in bars:
            self._store[(b.symbol, b.bar_datetime, b.interval)] = b

    def list_range(
        self, symbol: str, start: datetime, end: datetime, interval: str = "minute60"
    ) -> list[IntradayPriceBarRecord]:
        return sorted(
            (
                b
                for (s, dt, itv), b in self._store.items()
                if s == symbol and itv == interval and start <= dt <= end
            ),
            key=lambda b: b.bar_datetime,
        )


class InMemoryDisclosureRepository(DisclosureRepository):
    def __init__(self) -> None:
        self._store: dict[str, DisclosureRecord] = {}

    def save_many(self, items: list[DisclosureRecord]) -> None:
        for item in items:
            self._store.setdefault(item.id, item)

    def list_recent(self, symbol: str, limit: int = 5) -> list[DisclosureRecord]:
        items = [d for d in self._store.values() if d.symbol == symbol]
        items.sort(key=lambda d: d.rcept_dt, reverse=True)
        return items[:limit]


class InMemoryNewsRepository(NewsRepository):
    def __init__(self) -> None:
        self._store: dict[str, NewsRecord] = {}

    def save_many(self, items: list[NewsRecord]) -> None:
        for item in items:
            self._store[item.id] = item

    def list_recent(self, symbol: str, limit: int = 5) -> list[NewsRecord]:
        items = [n for n in self._store.values() if n.symbol == symbol]
        items.sort(key=lambda n: n.published_at, reverse=True)
        return items[:limit]


class InMemoryAIScoreCacheRepository(AIScoreCacheRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str, str, str], AIScoreCacheRecord] = {}

    def get(self, subject_type: str, subject_id: str, prompt_version: str, model: str) -> AIScoreCacheRecord | None:
        return self._store.get((subject_type, subject_id, prompt_version, model))

    def save(self, record: AIScoreCacheRecord) -> None:
        self._store[(record.subject_type, record.subject_id, record.prompt_version, record.model)] = record
