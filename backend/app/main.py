from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, backtest, data, nodes, workflows
from app.api.ws import router as ws_router
from app.config import get_settings
from app.dependencies import build_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    container = build_container(settings)
    app.state.container = container
    container.scheduler_service.start()
    container.worker_pool.start()
    try:
        yield
    finally:
        container.scheduler_service.stop()
        container.worker_pool.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="nemo-stock API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(nodes.router)
    app.include_router(workflows.router)
    app.include_router(backtest.router)
    app.include_router(data.router)
    app.include_router(ws_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
