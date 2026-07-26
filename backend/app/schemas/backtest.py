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


class DailyRunOut(BaseModel):
    date: str
    run_id: str


class TradeOut(BaseModel):
    date: str
    run_id: str
    order_id: str
    symbol: str
    side: str
    qty: int
    price: float
    status: str
    reason: str | None = None
    realized_pnl: float | None = None


class PricePointOut(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class NewsMarkerOut(BaseModel):
    date: str
    news_id: str
    title: str
    published_at: str
    source: str
    used: bool


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
    daily_runs: list[DailyRunOut] = Field(default_factory=list)
    universe: list[str] = Field(default_factory=list)
    trades: list[TradeOut] = Field(default_factory=list)
    created_at: datetime
