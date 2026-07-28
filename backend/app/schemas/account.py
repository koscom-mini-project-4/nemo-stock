from __future__ import annotations

from pydantic import BaseModel, Field


class PositionOut(BaseModel):
    symbol: str
    qty: int
    avg_price: float


class AccountSummaryOut(BaseModel):
    cash: float
    equity: float
    positions: list[PositionOut] = Field(default_factory=list)
