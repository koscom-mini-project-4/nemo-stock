from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateDraftRequest(BaseModel):
    idea: str = Field(min_length=1, description="자연어 투자 아이디어")
    universe: list[str] | None = None


class GenerateDraftResponse(BaseModel):
    name: str
    graph: dict[str, Any]
    disclaimer: str
