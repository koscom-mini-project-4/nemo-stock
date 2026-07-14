from __future__ import annotations

from fastapi import Depends, Request

from app.ai.base import AIClient
from app.dependencies import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_ai_client(container: Container = Depends(get_container)) -> AIClient:
    """별도 의존성으로 분리해 테스트에서 app.dependency_overrides로 손쉽게 대체할 수 있게 한다."""
    return container.ai_client
