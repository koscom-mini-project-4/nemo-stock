"""애플리케이션 컨테이너.

DAO/Provider/엔진/큐/스케줄러/워커풀 인스턴스를 한 곳에서 조립한다.
FastAPI Depends는 이 컨테이너를 request.app.state.container에서 꺼내 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from app.auth.security import hash_password
from app.broker.base import OrderExecutionProvider
from app.broker.dummy import DummyOrderExecutionProvider
from app.config import Settings
from app.dao.base import (
    NodeEventRepository,
    RunRepository,
    UserRecord,
    UserRepository,
    WorkflowRepository,
)
from app.dao.sqlite.database import init_db, make_engine, make_session_factory
from app.dao.sqlite.repositories import (
    SqliteNodeEventRepository,
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
    event_bus: EventBus
    market_data: MarketDataProvider
    broker: OrderExecutionProvider
    engine: WorkflowEngine
    trigger_queue: TriggerQueue
    scheduler_service: SchedulerService
    worker_pool: WorkerPool


def build_container(settings: Settings) -> Container:
    load_all_nodes()

    engine_db = make_engine(settings.database_url)
    init_db(engine_db)
    session_factory = make_session_factory(engine_db)

    user_repo = SqliteUserRepository(session_factory)
    workflow_repo = SqliteWorkflowRepository(session_factory)
    run_repo = SqliteRunRepository(session_factory)
    node_event_repo = SqliteNodeEventRepository(session_factory)

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
    worker_pool = WorkerPool(
        trigger_queue=trigger_queue,
        workflow_repo=workflow_repo,
        run_repo=run_repo,
        node_event_repo=node_event_repo,
        event_bus=event_bus,
        market_data=market_data,
        broker=broker,
        pool_size=settings.worker_pool_size,
    )

    return Container(
        settings=settings,
        session_factory=session_factory,
        user_repo=user_repo,
        workflow_repo=workflow_repo,
        run_repo=run_repo,
        node_event_repo=node_event_repo,
        event_bus=event_bus,
        market_data=market_data,
        broker=broker,
        engine=workflow_engine,
        trigger_queue=trigger_queue,
        scheduler_service=scheduler_service,
        worker_pool=worker_pool,
    )
