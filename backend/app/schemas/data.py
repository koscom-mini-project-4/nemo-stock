from __future__ import annotations

from datetime import date, datetime
from typing import Any

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


class ClassifiedNewsItemIn(BaseModel):
    """외부 AI가 이미 분류(Depth 1/2/3)한 뉴스 1건. app/nodes/data/news_signal.py(11개 노드,
    koscom_nemonemo fork 포트, DESIGN.md §0-6)가 쓰는 news_signals 테이블에 적재된다."""

    title: str = ""
    body: str = ""
    published_at: datetime
    symbol: str | None = None
    classification: dict[str, Any]  # {"depth_1": {...}, "depth_2": {...}, "depth_3": {...}}


class ClassifiedNewsIngestRequest(BaseModel):
    items: list[ClassifiedNewsItemIn] = Field(default_factory=list)


class NewsUpdateRequest(BaseModel):
    force: bool = False
    # §0-12: 주어지면 이번 1회 갱신만 라이브러리 기본 크롤 설정을 오버라이드한다(전역
    # 설정은 안 바꿈). days=최근 며칠치, keywords=헤드라인 부분일치 필터.
    days: int | None = None
    keywords: list[str] | None = None
    # 주어지면 이번 1회 AI 분류 호출만 다른 모델을 쓴다(전역 openai_model은 안 바꿈,
    # §0-19 model_override 패턴과 동일).
    model: str | None = None
    # 주어지면 날짜당 최대 목록 페이지 수를 이번 1회만 오버라이드한다(기본 crawl_max_pages=5,
    # 특정 키워드 검색 시 페이지 더 깊이 훑고 싶을 때).
    max_pages: int | None = None


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
