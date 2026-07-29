from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request

from app.ai.base import AIClient
from app.dao.base import IntradayPriceBarRepository
from app.data_ingestion.naver_price_client import NaverStockChartClient
from app.dependencies import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_ai_client(container: Container = Depends(get_container)) -> AIClient:
    """별도 의존성으로 분리해 테스트에서 app.dependency_overrides로 손쉽게 대체할 수 있게 한다."""
    return container.ai_client


def get_strategy_ai_client(container: Container = Depends(get_container)) -> AIClient:
    """전략 생성(AI 초안 생성) 전용 AIClient(§0-19) — AI_MODEL_STRATEGY가 설정돼 있으면
    나머지 AI 기능(챗봇/백테스트 설명/뉴스 감성 등)과 다른 모델을 쓴다."""
    return container.strategy_ai_client


def get_intraday_price_bar_repo(container: Container = Depends(get_container)) -> IntradayPriceBarRepository:
    return container.intraday_price_bar_repo


def get_price_ingest_client() -> Iterator[NaverStockChartClient]:
    """백테스트 자동 시세 수집용 클라이언트. 별도 의존성으로 분리해 테스트에서 대체 가능하게 한다."""
    client = NaverStockChartClient()
    try:
        yield client
    finally:
        client.close()
