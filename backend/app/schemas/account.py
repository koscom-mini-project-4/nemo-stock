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
    # 평가자산 수익률 계산 기준선(포트폴리오 최초 시드 현금). Settings.initial_portfolio_cash.
    initial_cash: float = 0.0


class WatchlistItemOut(BaseModel):
    symbol: str
    name: str | None = None
    created_at: datetime


class WatchlistAddRequest(BaseModel):
    symbol: str


class PositionUpsertRequest(BaseModel):
    qty: int
    avg_price: float
