"""공공데이터(가격/공시/뉴스) 적재 API.

- /data/ingest/prices/manual, /data/ingest/news/manual: 임의 값을 직접 넣어 테스트/백테스트 데이터를 만든다.
- /data/ingest/prices/public: 공공데이터포털 금융위원회_주식시세정보 API로 실제 일봉을 수집한다
  (DATA_GO_KR_SERVICE_KEY 필요, 없으면 400).
- /data/ingest/disclosures/public: OpenDART 공시 목록을 수집한다(DART_API_KEY 필요, 없으면 400).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container, get_intraday_price_bar_repo, get_price_ingest_client
from app.auth.security import get_current_username
from app.dao.base import DisclosureRecord, IntradayPriceBarRepository, NewsRecord, PriceBarRecord
from app.data_ingestion.auto_ingest import ensure_price_data
from app.data_ingestion.naver_price_client import NaverStockChartClient
from app.data_ingestion.opendart_client import OpenDartAPIError, OpenDartClient
from app.data_ingestion.public_data_price import PublicDataAPIError, PublicDataPriceClient
from app.dependencies import Container
from app.market_data.symbol_master import search_symbols
from app.news_signals.ingest import build_news_signal, classify_and_build_signal
from app.schemas.backtest import PricePointOut
from app.schemas.data import (
    ClassifiedNewsIngestRequest,
    IngestResponse,
    ManualNewsIngestRequest,
    ManualPriceIngestRequest,
    NewsUpdateRequest,
    NewsUpdateResponse,
    PublicDisclosureIngestRequest,
    PublicPriceIngestRequest,
    SymbolOut,
)

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_username)])


@router.get("/symbols", response_model=list[SymbolOut])
def get_symbols(q: str = "") -> list[SymbolOut]:
    """종목코드/한글 종목명으로 검색한다(부분 일치). q가 비어 있으면 전체 목록.

    정적 매핑(app/market_data/symbol_master.py)만 검색 대상이다 — 매핑에 없는 임의
    종목코드는 워크플로에서 여전히 자유롭게 쓸 수 있지만 이 검색에는 나타나지 않는다.
    """
    return [SymbolOut(symbol=s.symbol, name=s.name) for s in search_symbols(q)]


@router.get("/prices/{symbol}", response_model=list[PricePointOut])
def get_prices(
    symbol: str,
    days: int = 90,
    container: Container = Depends(get_container),
    intraday_repo: IntradayPriceBarRepository = Depends(get_intraday_price_bar_repo),
    price_client: NaverStockChartClient = Depends(get_price_ingest_client),
) -> list[PricePointOut]:
    """대시보드 등에서 백테스트와 무관하게 특정 종목의 최근 일봉을 조회한다.

    /backtest/{id}/prices와 달리 특정 백테스트 결과에 종속되지 않는다. 해당 구간에 데이터가
    전혀 없으면(auto_ingest_prices=true일 때) app/data_ingestion/auto_ingest.py와 동일하게
    Naver 차트 API로 자동 수집한다.
    """
    end = date.today()
    start = end - timedelta(days=days)

    if container.settings.auto_ingest_prices:
        ensure_price_data(container.price_bar_repo, intraday_repo, price_client, symbol, start, end)

    bars = container.price_bar_repo.list_range(symbol, start, end)
    return [
        PricePointOut(
            date=b.trade_date.isoformat(), open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume
        )
        for b in bars
    ]


@router.post("/ingest/prices/manual", response_model=IngestResponse)
def ingest_manual_prices(payload: ManualPriceIngestRequest, container: Container = Depends(get_container)) -> IngestResponse:
    records = [
        PriceBarRecord(
            symbol=payload.symbol,
            trade_date=bar.trade_date,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            source="manual",
        )
        for bar in payload.bars
    ]
    container.price_bar_repo.save_many(records)
    return IngestResponse(ingested=len(records))


@router.post("/ingest/prices/public", response_model=IngestResponse)
def ingest_public_prices(payload: PublicPriceIngestRequest, container: Container = Depends(get_container)) -> IngestResponse:
    if not container.settings.data_go_kr_service_key:
        raise HTTPException(status_code=400, detail="DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")
    with PublicDataPriceClient(container.settings.data_go_kr_service_key) as client:
        try:
            bars = client.fetch_daily_prices(payload.symbol, payload.start, payload.end)
        except PublicDataAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    container.price_bar_repo.save_many(bars)
    return IngestResponse(ingested=len(bars))


@router.post("/ingest/news/manual", response_model=IngestResponse)
def ingest_manual_news(payload: ManualNewsIngestRequest, container: Container = Depends(get_container)) -> IngestResponse:
    """뉴스 원문을 적재한다. AI 키가 있으면 즉석 분류해 뉴스 신호(충격량, §0-6)까지 함께 저장한다."""
    records = [
        NewsRecord(
            id=str(uuid.uuid4()),
            symbol=payload.symbol,
            title=item.title,
            body=item.body,
            published_at=item.published_at,
            source="manual",
        )
        for item in payload.items
    ]
    container.news_repo.save_many(records)

    # AI가 설정되어 있으면 수집 시점에 분류 → 충격량 계산 → 신호 저장(best-effort, 분류 실패는
    # 원문 적재까지만 인정하고 넘어간다 — app/nodes/data/news_signal.py 11개 노드가 이 신호를 읽는다).
    if container.ai_client.available:
        signals = []
        for rec, item in zip(records, payload.items):
            try:
                signals.append(
                    classify_and_build_signal(
                        container.ai_client,
                        f"{item.title}: {item.body}",
                        item.published_at,
                        news_id=rec.id,
                        symbol=payload.symbol,
                        source="manual",
                    )
                )
            except Exception:  # noqa: BLE001
                continue
        container.news_signal_repo.save_many(signals)

    return IngestResponse(ingested=len(records))


@router.post("/ingest/news/classified", response_model=IngestResponse)
def ingest_classified_news(
    payload: ClassifiedNewsIngestRequest, container: Container = Depends(get_container)
) -> IngestResponse:
    """외부에서 이미 분류(Depth 1/2/3)된 뉴스를 받아 충격량을 계산해 신호로 적재한다(§0-6).

    "메인 서버가 정제된 JSON을 받아온 시점부터"의 계산 진입점 — AI 호출이 필요 없어 자체
    뉴스 분류 파이프라인(예: back-news-analysis, 외부 크롤러)의 결과를 그대로 넣을 수 있다.
    symbol이 있으면 원문 뉴스 레코드도 함께 저장해 data.news 노드에서도 조회 가능하게 한다.
    """
    signals = []
    news_records = []
    for item in payload.items:
        news_id = str(uuid.uuid4())
        signals.append(
            build_news_signal(
                item.classification,
                item.published_at,
                news_id=news_id,
                symbol=item.symbol,
                source="classified",
            )
        )
        if item.symbol:
            news_records.append(
                NewsRecord(
                    id=news_id, symbol=item.symbol, title=item.title, body=item.body,
                    published_at=item.published_at, source="classified",
                )
            )
    container.news_signal_repo.save_many(signals)
    if news_records:
        container.news_repo.save_many(news_records)
    return IngestResponse(ingested=len(signals))


@router.post("/ingest/disclosures/public", response_model=IngestResponse)
def ingest_public_disclosures(
    payload: PublicDisclosureIngestRequest, container: Container = Depends(get_container)
) -> IngestResponse:
    if not container.settings.dart_api_key:
        raise HTTPException(status_code=400, detail="DART_API_KEY가 설정되지 않았습니다.")
    with OpenDartClient(container.settings.dart_api_key) as client:
        try:
            items = client.fetch_disclosures(payload.start, payload.end, stock_codes=payload.symbols)
        except OpenDartAPIError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    records = [
        DisclosureRecord(
            id=item.rcept_no,
            symbol=item.stock_code or "",
            corp_name=item.corp_name,
            report_nm=item.report_nm,
            rcept_dt=item.rcept_dt,
            source="opendart",
        )
        for item in items
        if item.stock_code
    ]
    container.disclosure_repo.save_many(records)
    return IngestResponse(ingested=len(records))


@router.post("/news/update", response_model=NewsUpdateResponse, response_model_by_alias=False)
def update_news_signal(payload: NewsUpdateRequest, container: Container = Depends(get_container)) -> NewsUpdateResponse:
    """뉴스 신호 파이프라인(ai.news_signal 노드가 쓰는 app/vendor/news_classifier)의 크롤링+AI
    분류를 명시적으로 트리거한다. ai.news_signal 노드는 params.auto_update=true면 실행 시점에
    스스로 이 갱신을 수행하지만(내부적으로 30분 쓰로틀), auto_update=false로 꺼둔 워크플로(예:
    백테스트처럼 실행 중 네트워크/AI 호출을 원치 않는 경우)나 다른 기능(대시보드 새로고침 등)이
    독립적으로 크롤링을 트리거하고 싶을 때 이 엔드포인트를 쓴다."""
    trader = container.news_trader_factory(auto_update=False)
    try:
        result = trader.update(force=payload.force)
    finally:
        trader.close()
    return NewsUpdateResponse.model_validate(result)


@router.get("/news/stats")
def get_news_stats(container: Container = Depends(get_container)) -> dict[str, Any]:
    """뉴스 신호 파이프라인 DB 전체 요약(뉴스/클러스터/분류 건수, strength 분포 등).
    관리자 페이지의 "뉴스 분석 현황"이 사용한다. NewsTrader.stats()를 그대로 반환한다."""
    trader = container.news_trader_factory(auto_update=False)
    try:
        return trader.stats()
    finally:
        trader.close()


@router.get("/news/clusters")
def get_news_clusters(start: date, end: date, container: Container = Depends(get_container)) -> list[dict[str, Any]]:
    """기간 내 뉴스 클러스터 목록(대표제목/최초발생일/strength/뉴스건수).

    NewsTrader.clusters()는 저장된 시각(예: "2026-07-28 14:25:15")과 문자열로 직접 비교하므로,
    날짜만(예: "2026-07-28") 넘기면 그날 자정 이후 데이터가 상한에 걸려 누락된다(실 서버 검증
    중 발견) — /backtest/{id}/news/all과 동일하게 하루 전체([00:00:00, 23:59:59])로 넓혀서 넘긴다.
    """
    trader = container.news_trader_factory(auto_update=False)
    try:
        return trader.clusters(
            datetime.combine(start, time.min).strftime("%Y-%m-%d %H:%M:%S"),
            datetime.combine(end, time.max).strftime("%Y-%m-%d %H:%M:%S"),
        )
    finally:
        trader.close()
