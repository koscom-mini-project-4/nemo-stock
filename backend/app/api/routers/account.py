"""계좌(현금/평가자산/보유 포지션) 조회 API.

단일 관리자 계정 PoC(_DEFAULT_USER_ID = "admin")라 모든 워크플로가 이 계좌 하나를
공유한다(app/broker/persistent_dummy.py 참고) — 대시보드에 "워크플로별 손익"이 아니라
"전체 계좌 현황"을 보여주는 이유다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.auth.security import get_current_username
from app.dependencies import Container
from app.schemas.account import AccountSummaryOut, PositionOut

router = APIRouter(prefix="/account", tags=["account"], dependencies=[Depends(get_current_username)])


@router.get("/summary", response_model=AccountSummaryOut)
def get_account_summary(container: Container = Depends(get_container)) -> AccountSummaryOut:
    balance = container.broker.get_balance()
    positions = container.broker.get_positions()
    return AccountSummaryOut(
        cash=balance.cash,
        equity=balance.equity,
        positions=[PositionOut(symbol=p.symbol, qty=p.qty, avg_price=p.avg_price) for p in positions],
    )
