from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.security import get_current_username
from app.nodes.base import node_registry_schema

router = APIRouter(prefix="/nodes", tags=["nodes"], dependencies=[Depends(get_current_username)])


@router.get("", response_model=list[dict[str, Any]])
def list_nodes() -> list[dict[str, Any]]:
    return node_registry_schema()
