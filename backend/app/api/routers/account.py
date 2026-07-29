"""계좌(현금/평가자산/보유 포지션) 조회 API.

단일 관리자 계정 PoC(_DEFAULT_USER_ID = "admin")라 모든 워크플로가 이 계좌 하나를
공유한다(app/broker/persistent_dummy.py 참고) — 대시보드에 "워크플로별 손익"이 아니라
"전체 계좌 현황"을 보여주는 이유다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.auth.security import get_current_username
from app.dependencies import Container
from app.market_data.symbol_master import get_symbol_name
from app.schemas.account import (
    AccountSummaryOut,
    PositionOut,
    PositionUpsertRequest,
    WatchlistAddRequest,
    WatchlistItemOut,
)

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(get_current_username)])

_DEFAULT_USER_ID = "admin"  # 단일 계정 PoC


@router.get("/summary", response_model=AccountSummaryOut)
def get_account_summary(container: Container = Depends(get_container)) -> AccountSummaryOut:
    balance = container.broker.get_balance()
    positions = container.broker.get_positions()
    return AccountSummaryOut(
        cash=balance.cash,
        equity=balance.equity,
        positions=[PositionOut(symbol=p.symbol, qty=p.qty, avg_price=p.avg_price) for p in positions],
    )


@router.put("/positions/{symbol}", response_model=PositionOut)
def upsert_position(
    symbol: str, payload: PositionUpsertRequest, container: Container = Depends(get_container)
) -> PositionOut:
    """보유 포지션을 수동으로 추가/수정한다(테스트 실행 중 잘못 만들어진 포지션 정정 등).
    새 종목이면 추가, 기존 종목이면 수량/평단가를 덮어쓴다."""
    if payload.qty <= 0:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다. 삭제는 DELETE를 사용하세요.")
    container.portfolio_repo.upsert_position(_DEFAULT_USER_ID, symbol, payload.qty, payload.avg_price)
    return PositionOut(symbol=symbol, qty=payload.qty, avg_price=payload.avg_price)


@router.delete("/positions/{symbol}", status_code=204)
def delete_position(symbol: str, container: Container = Depends(get_container)) -> None:
    container.portfolio_repo.upsert_position(_DEFAULT_USER_ID, symbol, 0, 0.0)


@router.get("/watchlist", response_model=list[WatchlistItemOut])
def list_watchlist(container: Container = Depends(get_container)) -> list[WatchlistItemOut]:
    items = container.watchlist_repo.list(_DEFAULT_USER_ID)
    return [
        WatchlistItemOut(symbol=i.symbol, name=get_symbol_name(i.symbol), created_at=i.created_at) for i in items
    ]


@router.post("/watchlist", response_model=list[WatchlistItemOut], status_code=201)
def add_watchlist_item(
    payload: WatchlistAddRequest, container: Container = Depends(get_container)
) -> list[WatchlistItemOut]:
    container.watchlist_repo.add(_DEFAULT_USER_ID, payload.symbol)
    return list_watchlist(container)


@router.delete("/watchlist/{symbol}", status_code=204)
def remove_watchlist_item(symbol: str, container: Container = Depends(get_container)) -> None:
    container.watchlist_repo.remove(_DEFAULT_USER_ID, symbol)
