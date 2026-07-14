from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    workflow_id: str
    universe: list[str]
    start_date: date
    end_date: date
    initial_capital: float = 10_000_000.0


class EquityPoint(BaseModel):
    date: str
    equity: float


class BacktestResultOut(BaseModel):
    id: str
    workflow_id: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    mdd_pct: float
    volatility_pct: float
    win_rate_pct: float
    profit_loss_ratio: float | None
    trade_count: int
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    created_at: datetime
