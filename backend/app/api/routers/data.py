"""공공데이터(가격) 적재 API.

- /data/ingest/prices/manual: 임의 값을 직접 넣어 테스트/백테스트 데이터를 만든다.
- /data/ingest/prices/public: 공공데이터포털 금융위원회_주식시세정보 API로 실제 일봉을 수집한다
  (DATA_GO_KR_SERVICE_KEY 필요, 없으면 400).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.auth.security import get_current_username
from app.dao.base import PriceBarRecord
from app.data_ingestion.public_data_price import PublicDataAPIError, PublicDataPriceClient
from app.dependencies import Container
from app.schemas.data import IngestResponse, ManualPriceIngestRequest, PublicPriceIngestRequest

router = APIRouter(prefix="/data", tags=["data"], dependencies=[Depends(get_current_username)])


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
