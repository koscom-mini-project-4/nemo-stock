from __future__ import annotations

from datetime import date, datetime

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


class NewsItemIn(BaseModel):
    title: str
    body: str
    published_at: datetime


class ManualNewsIngestRequest(BaseModel):
    symbol: str
    items: list[NewsItemIn] = Field(default_factory=list)


class PublicDisclosureIngestRequest(BaseModel):
    symbols: list[str]
    start: date
    end: date
