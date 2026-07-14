from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PriceBarIn(BaseModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class ManualPriceIngestRequest(BaseModel):
    symbol: str
    bars: list[PriceBarIn] = Field(default_factory=list)


class PublicPriceIngestRequest(BaseModel):
    symbol: str
    start: date
    end: date


class IngestResponse(BaseModel):
    ingested: int
