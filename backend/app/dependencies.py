"""애플리케이션 컨테이너.

DAO/Provider/엔진/큐/스케줄러/워커풀 인스턴스를 한 곳에서 조립한다.
FastAPI Depends는 이 컨테이너를 request.app.state.container에서 꺼내 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.ai.base import AIClient
from app.ai.openai_client import OpenAIClient
from app.auth.security import hash_password
from app.broker.base import OrderExecutionProvider
from app.broker.dummy import DummyOrderExecutionProvider
from app.broker.persistent_dummy import PersistentOrderExecutionProvider
from app.broker.toss_adapter import TossInvestOrderExecutionProvider
from app.config import Settings
from app.dao.base import (
    AIScoreCacheRepository,
    BacktestResultRepository,
    DisclosureRepository,
    IntradayPriceBarRepository,
    NewsRepository,
    NodeEventRepository,
    PortfolioRepository,
    PriceBarRepository,
    RunRepository,
    UserRecord,
    UserRepository,
    WorkflowRepository,
)
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteAIScoreCacheRepository,
    SqliteBacktestResultRepository,
    SqliteDisclosureRepository,
    SqliteIntradayPriceBarRepository,
    SqliteNewsRepository,
    SqliteNodeEventRepository,
    SqlitePortfolioRepository,
    SqlitePriceBarRepository,
    SqliteRunRepository,
    SqliteUserRepository,
    SqliteWorkflowRepository,
)
from app.market_data.base import MarketDataProvider
from app.market_data.dummy import DummyMarketDataProvider
from app.market_data.koscom_adapter import KoscomMarketDataProvider
from app.market_data.toss_adapter import TossInvestMarketDataProvider
from app.nodes import load_all_nodes
from app.trigger.queue import InMemoryTriggerQueue, TriggerQueue
from app.trigger.scheduler_service import SchedulerService
from app.trigger.worker_pool import WorkerPool
from app.workflow.engine import WorkflowEngine
from app.workflow.events import EventBus, InMemoryEventBus


@dataclass
class Container:
    settings: Settings
    session_factory: sessionmaker
    user_repo: UserRepository
    workflow_repo: WorkflowRepository
    run_repo: RunRepository
    node_event_repo: NodeEventRepository
    price_bar_repo: PriceBarRepository
    intraday_price_bar_repo: IntradayPriceBarRepository
    backtest_result_repo: BacktestResultRepository
    disclosure_repo: DisclosureRepository
    news_repo: NewsRepository
    ai_score_cache_repo: AIScoreCacheRepository
    portfolio_repo: PortfolioRepository
    ai_client: AIClient
    event_bus: EventBus
    market_data: MarketDataProvider
    broker: OrderExecutionProvider
    engine: WorkflowEngine
    trigger_queue: TriggerQueue
    scheduler_service: SchedulerService
    worker_pool: WorkerPool

    def node_providers(self) -> dict[str, Any]:
        """market_data/broker 외에 노드가 필요로 하는 추가 의존성(AI/뉴스/공시)."""
        return {
            "ai_client": self.ai_client,
            "ai_score_cache_repo": self.ai_score_cache_repo,
            "news_repo": self.news_repo,
            "disclosure_repo": self.disclosure_repo,
        }


def _build_market_data_provider(settings: Settings) -> MarketDataProvider:
    if settings.market_data_provider == "toss":
        if not settings.toss_client_id or not settings.toss_client_secret:
            raise RuntimeError(
                "MARKET_DATA_PROVIDER=toss 이지만 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET이 설정되지 않았습니다."
            )
        return TossInvestMarketDataProvider(
            settings.toss_client_id, settings.toss_client_secret, settings.toss_base_url
        )
    if settings.market_data_provider == "koscom":
        if not settings.koscom_cust_id or not settings.koscom_auth_key:
            raise RuntimeError(
                "MARKET_DATA_PROVIDER=koscom 이지만 KOSCOM_CUST_ID/KOSCOM_AUTH_KEY가 설정되지 않았습니다."
            )
        return KoscomMarketDataProvider(
            settings.koscom_cust_id, settings.koscom_auth_key, settings.koscom_base_url
        )
    # "historical"은 백테스트 전용(BacktestRunner가 자체 생성)이라 라이브 컨테이너에서는 dummy로 폴백한다.
    return DummyMarketDataProvider()


def _build_order_provider(
    settings: Settings, portfolio_repo: PortfolioRepository | None = None, user_id: str | None = None
) -> OrderExecutionProvider:
    if settings.order_provider == "toss":
        if not settings.toss_client_id or not settings.toss_client_secret or not settings.toss_account_id:
            raise RuntimeError(
                "ORDER_PROVIDER=toss 이지만 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET/TOSS_ACCOUNT_ID가 설정되지 않았습니다."
            )
        return TossInvestOrderExecutionProvider(
            settings.toss_client_id, settings.toss_client_secret, settings.toss_base_url, settings.toss_account_id
        )
    if portfolio_repo is not None and user_id is not None:
        return PersistentOrderExecutionProvider(
            portfolio_repo, user_id, default_initial_cash=settings.initial_portfolio_cash
        )
    return DummyOrderExecutionProvider(initial_cash=settings.initial_portfolio_cash)


def build_container(settings: Settings) -> Container:
    load_all_nodes()

    engine_db = make_engine(settings.database_url)
    init_db(engine_db)
    session_factory = make_session_factory(engine_db)

    user_repo = SqliteUserRepository(session_factory)
    workflow_repo = SqliteWorkflowRepository(session_factory)
    run_repo = SqliteRunRepository(session_factory)
    node_event_repo = SqliteNodeEventRepository(session_factory)
    price_bar_repo = SqlitePriceBarRepository(session_factory)
    intraday_price_bar_repo = SqliteIntradayPriceBarRepository(session_factory)
    backtest_result_repo = SqliteBacktestResultRepository(session_factory)
    disclosure_repo = SqliteDisclosureRepository(session_factory)
    news_repo = SqliteNewsRepository(session_factory)
    ai_score_cache_repo = SqliteAIScoreCacheRepository(session_factory)
    portfolio_repo = SqlitePortfolioRepository(session_factory)
    ai_client: AIClient = OpenAIClient(settings.openai_api_key, settings.openai_model)

    # 최초 기동 시 단일 관리자 계정 부트스트랩
    admin_id = "admin"
    existing = user_repo.get_by_username(settings.admin_username)
    if existing is None:
        user_repo.upsert(
            UserRecord(
                id=admin_id,
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
        )
    # 포트폴리오(현금) 최초 시드 — 이미 체결 이력이 있으면(cash 레코드 존재) 건드리지 않는다.
    if portfolio_repo.get_cash(admin_id) is None:
        portfolio_repo.set_cash(admin_id, settings.initial_portfolio_cash)

    event_bus = InMemoryEventBus()
    market_data = _build_market_data_provider(settings)
    broker = _build_order_provider(settings, portfolio_repo, admin_id)
    workflow_engine = WorkflowEngine(event_bus)
    trigger_queue = InMemoryTriggerQueue()

    scheduler_service = SchedulerService(
        workflow_repo=workflow_repo,
        trigger_queue=trigger_queue,
        tick_seconds=settings.scheduler_tick_seconds,
    )
    node_providers = {
        "ai_client": ai_client,
        "ai_score_cache_repo": ai_score_cache_repo,
        "news_repo": news_repo,
        "disclosure_repo": disclosure_repo,
    }
    worker_pool = WorkerPool(
        trigger_queue=trigger_queue,
        workflow_repo=workflow_repo,
        run_repo=run_repo,
        node_event_repo=node_event_repo,
        event_bus=event_bus,
        market_data=market_data,
        broker=broker,
        pool_size=settings.worker_pool_size,
        extra_providers=node_providers,
    )

    return Container(
        settings=settings,
        session_factory=session_factory,
        user_repo=user_repo,
        workflow_repo=workflow_repo,
        run_repo=run_repo,
        node_event_repo=node_event_repo,
        price_bar_repo=price_bar_repo,
        intraday_price_bar_repo=intraday_price_bar_repo,
        backtest_result_repo=backtest_result_repo,
        disclosure_repo=disclosure_repo,
        news_repo=news_repo,
        ai_score_cache_repo=ai_score_cache_repo,
        portfolio_repo=portfolio_repo,
        ai_client=ai_client,
        event_bus=event_bus,
        market_data=market_data,
        broker=broker,
        engine=workflow_engine,
        trigger_queue=trigger_queue,
        scheduler_service=scheduler_service,
        worker_pool=worker_pool,
    )
