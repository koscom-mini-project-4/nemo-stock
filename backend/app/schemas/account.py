from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PositionOut(BaseModel):
    symbol: str
    qty: int
    avg_price: float


class AccountSummaryOut(BaseModel):
    cash: float
    equity: float
    positions: list[PositionOut] = Field(default_factory=list)


class WatchlistItemOut(BaseModel):
    symbol: str
    name: str | None = None
    created_at: datetime


class WatchlistAddRequest(BaseModel):
    symbol: str


class PositionUpsertRequest(BaseModel):
    qty: int
    avg_price: float
