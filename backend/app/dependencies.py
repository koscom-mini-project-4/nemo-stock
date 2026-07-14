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
from app.config import Settings
from app.dao.base import (
    AIScoreCacheRepository,
    BacktestResultRepository,
    DisclosureRepository,
    NewsRepository,
    NodeEventRepository,
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
    SqliteNewsRepository,
    SqliteNodeEventRepository,
    SqlitePriceBarRepository,
    SqliteRunRepository,
    SqliteUserRepository,
    SqliteWorkflowRepository,
)
from app.market_data.base import MarketDataProvider
from app.market_data.dummy import DummyMarketDataProvider
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
    backtest_result_repo: BacktestResultRepository
    disclosure_repo: DisclosureRepository
    news_repo: NewsRepository
    ai_score_cache_repo: AIScoreCacheRepository
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
    backtest_result_repo = SqliteBacktestResultRepository(session_factory)
    disclosure_repo = SqliteDisclosureRepository(session_factory)
    news_repo = SqliteNewsRepository(session_factory)
    ai_score_cache_repo = SqliteAIScoreCacheRepository(session_factory)
    ai_client: AIClient = OpenAIClient(settings.openai_api_key, settings.openai_model)

    # 최초 기동 시 단일 관리자 계정 부트스트랩
    existing = user_repo.get_by_username(settings.admin_username)
    if existing is None:
        user_repo.upsert(
            UserRecord(
                id="admin",
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
        )

    event_bus = InMemoryEventBus()
    market_data = DummyMarketDataProvider()
    broker = DummyOrderExecutionProvider()
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
        backtest_result_repo=backtest_result_repo,
        disclosure_repo=disclosure_repo,
        news_repo=news_repo,
        ai_score_cache_repo=ai_score_cache_repo,
        ai_client=ai_client,
        event_bus=event_bus,
        market_data=market_data,
        broker=broker,
        engine=workflow_engine,
        trigger_queue=trigger_queue,
        scheduler_service=scheduler_service,
        worker_pool=worker_pool,
    )
