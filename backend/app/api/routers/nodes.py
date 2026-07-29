from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.nodes.base import node_registry_schema

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[dict[str, Any]])
def list_nodes() -> list[dict[str, Any]]:
    return node_registry_schema()
