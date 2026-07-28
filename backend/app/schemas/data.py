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


class SymbolOut(BaseModel):
    symbol: str
    name: str


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


class NewsUpdateRequest(BaseModel):
    force: bool = False


class NewsUpdateResponse(BaseModel):
    """ai.news_signal 노드가 쓰는 뉴스 신호 파이프라인(app/vendor/news_classifier)의
    update() 결과를 그대로 노출한다. force=False이고 마지막 갱신 후 update_interval_min이 안
    지났으면 건너뛰고 minutes_since_last_update만 채워진다."""

    skipped: bool = Field(alias="건너뜀")
    collected: int | None = Field(default=None, alias="수집")
    classified: int | None = Field(default=None, alias="분류")
    pending: int | None = Field(default=None, alias="미분류잔여")
    purged_clusters: int | None = Field(default=None, alias="삭제클러스터")
    minutes_since_last_update: float | None = Field(default=None, alias="마지막갱신후_분")

    model_config = {"populate_by_name": True}
