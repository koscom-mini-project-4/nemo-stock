"""Repository 인터페이스(DAO).

서비스 계층은 이 ABC들만 알고 있으면 되며, SQLite/인메모리/향후 다른 RDB
구현체는 이 인터페이스를 구현하기만 하면 교체 가능하다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

WorkflowStatus = Literal["draft", "active", "inactive"]
RunStatus = Literal["running", "success", "error"]


@dataclass
class UserRecord:
    id: str
    username: str
    password_hash: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowRecord:
    id: str
    user_id: str
    name: str
    graph: dict[str, Any]
    status: WorkflowStatus = "draft"
    schedule_interval_sec: int = 60
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class RunRecord:
    id: str
    workflow_id: str
    mode: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


@dataclass
class NodeEventRecord:
    id: str
    run_id: str
    node_id: str
    node_type: str
    status: str
    timestamp: datetime
    input_json: dict[str, Any] | None = None
    output_json: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None


@dataclass
class PriceBarRecord:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "public_data"


class UserRepository(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> UserRecord | None: ...

    @abstractmethod
    def upsert(self, user: UserRecord) -> None: ...


class WorkflowRepository(ABC):
    @abstractmethod
    def get(self, workflow_id: str) -> WorkflowRecord | None: ...

    @abstractmethod
    def save(self, workflow: WorkflowRecord) -> None: ...

    @abstractmethod
    def delete(self, workflow_id: str) -> None: ...

    @abstractmethod
    def list_by_user(self, user_id: str) -> list[WorkflowRecord]: ...

    @abstractmethod
    def list_active(self) -> list[WorkflowRecord]: ...


class RunRepository(ABC):
    @abstractmethod
    def save(self, run: RunRecord) -> None: ...

    @abstractmethod
    def get(self, run_id: str) -> RunRecord | None: ...

    @abstractmethod
    def list_by_workflow(self, workflow_id: str) -> list[RunRecord]: ...


class NodeEventRepository(ABC):
    @abstractmethod
    def save_many(self, events: list[NodeEventRecord]) -> None: ...

    @abstractmethod
    def list_by_run(self, run_id: str) -> list[NodeEventRecord]: ...


class PriceBarRepository(ABC):
    @abstractmethod
    def save_many(self, bars: list[PriceBarRecord]) -> None: ...

    @abstractmethod
    def list_range(self, symbol: str, start: date, end: date) -> list[PriceBarRecord]: ...


@dataclass
class BacktestResultRecord:
    id: str
    workflow_id: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    mdd_pct: float
    volatility_pct: float
    win_rate_pct: float
    profit_loss_ratio: float | None
    trade_count: int
    equity_curve: list[dict[str, Any]]  # [{"date": "YYYY-MM-DD", "equity": float}, ...]
    created_at: datetime = field(default_factory=datetime.now)


class BacktestResultRepository(ABC):
    @abstractmethod
    def save(self, result: BacktestResultRecord) -> None: ...

    @abstractmethod
    def get(self, result_id: str) -> BacktestResultRecord | None: ...

    @abstractmethod
    def list_by_workflow(self, workflow_id: str) -> list[BacktestResultRecord]: ...
