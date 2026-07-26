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


@dataclass
class PositionRecord:
    symbol: str
    qty: int
    avg_price: float


class PortfolioRepository(ABC):
    """계정별 현금/보유종목(포트폴리오) 영속 저장소.

    OrderExecutionProvider(app/broker/base.py)의 SQLite 기반 구현체가 이 ABC를 통해 매 체결마다
    현금/포지션을 읽고 쓴다 — 나중에 실제 증권사 API로 교체할 때도 이 ABC 자체는 바뀌지 않고
    OrderExecutionProvider의 새 구현체만 추가하면 된다.
    """

    @abstractmethod
    def get_cash(self, user_id: str) -> float | None: ...

    @abstractmethod
    def set_cash(self, user_id: str, cash: float) -> None: ...

    @abstractmethod
    def list_positions(self, user_id: str) -> list[PositionRecord]: ...

    @abstractmethod
    def upsert_position(self, user_id: str, symbol: str, qty: int, avg_price: float) -> None:
        """qty <= 0이면 해당 종목 포지션을 삭제한다."""
        ...


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
class IntradayPriceBarRecord:
    """시간봉(장중) 시세 1건. 하루에 여러 건 존재할 수 있어 PriceBarRecord와 분리한다."""

    symbol: str
    bar_datetime: datetime
    interval: str  # 예: "minute60"
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "naver"


class IntradayPriceBarRepository(ABC):
    @abstractmethod
    def save_many(self, bars: list[IntradayPriceBarRecord]) -> None: ...

    @abstractmethod
    def list_range(
        self, symbol: str, start: datetime, end: datetime, interval: str = "minute60"
    ) -> list[IntradayPriceBarRecord]: ...


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
    daily_runs: list[dict[str, Any]] = field(default_factory=list)  # [{"date": "...", "run_id": "..."}, ...]
    universe: list[str] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    """[{"date": "...", "run_id": "...", "order_id": "...", "symbol": "...", "side": "buy|sell",
    "qty": int, "price": float, "status": "...", "reason": str|None, "realized_pnl": float|None}, ...]"""
    created_at: datetime = field(default_factory=datetime.now)


class BacktestResultRepository(ABC):
    @abstractmethod
    def save(self, result: BacktestResultRecord) -> None: ...

    @abstractmethod
    def get(self, result_id: str) -> BacktestResultRecord | None: ...

    @abstractmethod
    def list_by_workflow(self, workflow_id: str) -> list[BacktestResultRecord]: ...


@dataclass
class DisclosureRecord:
    id: str  # OpenDART rcept_no
    symbol: str
    corp_name: str
    report_nm: str
    rcept_dt: date
    source: str = "opendart"


class DisclosureRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[DisclosureRecord]) -> None: ...

    @abstractmethod
    def list_recent(self, symbol: str, limit: int = 5) -> list[DisclosureRecord]: ...


@dataclass
class NewsRecord:
    id: str
    symbol: str
    title: str
    body: str
    published_at: datetime
    source: str = "manual"


class NewsRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[NewsRecord]) -> None: ...

    @abstractmethod
    def list_recent(self, symbol: str, limit: int = 5) -> list[NewsRecord]: ...

    @abstractmethod
    def get(self, news_id: str) -> NewsRecord | None: ...

    @abstractmethod
    def list_range(self, symbol: str, start: datetime, end: datetime) -> list[NewsRecord]: ...


@dataclass
class AIScoreCacheRecord:
    id: str
    subject_type: str  # "disclosure" | "news"
    subject_id: str
    prompt_version: str
    model: str
    score_json: dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)


class AIScoreCacheRepository(ABC):
    @abstractmethod
    def get(self, subject_type: str, subject_id: str, prompt_version: str, model: str) -> AIScoreCacheRecord | None: ...

    @abstractmethod
    def save(self, record: AIScoreCacheRecord) -> None: ...
