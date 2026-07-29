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


@dataclass
class WatchlistRecord:
    symbol: str
    created_at: datetime


class WatchlistRepository(ABC):
    """보유 여부와 무관하게 대시보드에서 추적하고 싶은 종목 목록(관심종목)."""

    @abstractmethod
    def list(self, user_id: str) -> list[WatchlistRecord]: ...

    @abstractmethod
    def add(self, user_id: str, symbol: str) -> None:
        """이미 있으면 조용히 무시한다(idempotent)."""
        ...

    @abstractmethod
    def remove(self, user_id: str, symbol: str) -> None:
        """없어도 에러 없이 조용히 넘어간다(idempotent)."""
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

    @abstractmethod
    def count(self) -> int:
        """저장된 백테스트 실행 결과 총 건수(관리자 페이지 사용량 통계용)."""


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
class NewsSignalRecord:
    """단일 뉴스의 분류(Depth 1/2/3) + 백엔드가 계산한 충격량(Impact) 점수 1행.

    koscom_nemonemo(fork)의 "뉴스 신호 파이프라인"(§0-6) 포트. 수집 시점에 AI 분류 결과로부터
    계산되어 저장되며, app/nodes/data/news_signal.py의 11개 노드가 섹터·기간으로 집계해
    매매 지표(섹터 모멘텀/공포 지수/테마 Z-Score 등)를 만든다. 우리 기존 NewsRecord(원문
    저장용)와는 별개 테이블/용도다.
    """

    id: str
    symbol: str | None
    sector: str | None
    direction: int
    event_type: str
    themes: list[str]
    base_impact: float
    sector_score: float
    domestic_score: float
    overseas_score: float
    published_at: datetime
    source: str = "manual"
    # 원문 뉴스 제목(§0-9) — 집계 지표(sector_momentum 등)가 "어떤 뉴스가 이 점수를 만들었는지"
    # 근거를 보여줄 때 쓴다(app/news_signals/aggregate.py::top_contributor). 과거 레코드는 없을
    # 수 있어 optional.
    title: str | None = None
    created_at: datetime = field(default_factory=datetime.now)


class NewsSignalRepository(ABC):
    @abstractmethod
    def save_many(self, items: list[NewsSignalRecord]) -> None: ...

    @abstractmethod
    def list_since(self, cutoff: datetime) -> list[NewsSignalRecord]:
        """published_at >= cutoff인 신호를 published_at 오름차순으로 반환(집계 입력)."""


@dataclass
class SymbolMasterRecord:
    """종목코드 -> 종목명/시장구분 매핑 1건(§0-10, 공공데이터포털 금융위원회_주식시세정보로
    동기화). `app/market_data/symbol_master.py`의 정적 8개 하드코딩 목록을 대체하는 durable
    캐시 — 이 레코드들이 부팅 시 in-memory 캐시로 로드된다."""

    symbol: str
    name: str
    market: str | None = None
    updated_at: datetime = field(default_factory=datetime.now)


class SymbolMasterRepository(ABC):
    @abstractmethod
    def upsert_many(self, items: list[SymbolMasterRecord]) -> None: ...

    @abstractmethod
    def list_all(self) -> list[SymbolMasterRecord]: ...

    @abstractmethod
    def get(self, symbol: str) -> SymbolMasterRecord | None: ...

    @abstractmethod
    def count(self) -> int: ...


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


@dataclass
class AIUsageRecord:
    """OpenAI 호출 1건의 사용량. 관리자 페이지의 "사용량 통계"(호출 수/토큰 수)가 집계 입력으로
    쓴다. purpose는 어느 기능이 호출했는지 구분하는 자유 문자열(예: "workflow_draft",
    "sentiment_score", "newsstock_classify") — 없으면 "unknown"으로 기록된다."""

    id: str
    purpose: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: datetime = field(default_factory=datetime.now)


class AIUsageRepository(ABC):
    @abstractmethod
    def save(self, record: AIUsageRecord) -> None: ...

    @abstractmethod
    def list_since(self, since: datetime | None) -> list[AIUsageRecord]:
        """since가 None이면 전체."""
