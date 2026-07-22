"""매수/매도 체결 시 현금·포지션 갱신 계산 (순수 함수).

DummyOrderExecutionProvider(인메모리, 백테스트 전용)와 PersistentOrderExecutionProvider(DB 영속,
라이브/테스트 전용)가 동일한 체결 계산식을 공유하도록 여기 한 곳에 둔다 — 두 구현이 각자
매수/매도 수식을 따로 들고 있으면 한쪽만 고쳐질 위험이 있다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.broker.base import OrderRequest, OrderResult, Position


def apply_fill(
    cash: float, position: Position, order: OrderRequest, fill_price: float | None
) -> tuple[float, Position, OrderResult]:
    """order를 fill_price 기준으로 체결 시도한다.

    반환: (갱신된 cash, 갱신된 position, 체결결과). 거부되면 cash/position은 입력값 그대로 반환된다.
    """
    if fill_price is None:
        return cash, position, _rejected(order, "체결 기준가(ref_price/limit_price)가 없습니다.")

    cost = fill_price * order.qty
    if order.side == "buy":
        if cost > cash:
            return cash, position, _rejected(order, "잔고 부족", fill_price)
        new_cash = cash - cost
        new_qty = position.qty + order.qty
        new_avg = (position.avg_price * position.qty + cost) / new_qty if new_qty else 0.0
        new_position = Position(order.symbol, new_qty, new_avg)
        return new_cash, new_position, _filled(order, fill_price)

    # sell
    if position.qty < order.qty:
        return cash, position, _rejected(order, "보유 수량 부족", fill_price)
    realized_pnl = (fill_price - position.avg_price) * order.qty
    new_cash = cash + cost
    remaining = position.qty - order.qty
    new_position = Position(order.symbol, remaining, position.avg_price if remaining else 0.0)
    return new_cash, new_position, _filled(order, fill_price, realized_pnl)


def _filled(order: OrderRequest, price: float, realized_pnl: float | None = None) -> OrderResult:
    return OrderResult(
        order_id=str(uuid.uuid4()),
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        qty=order.qty,
        price=price,
        status="filled",
        filled_at=datetime.now(),
        realized_pnl=realized_pnl,
    )


def _rejected(order: OrderRequest, reason: str, price: float = 0.0) -> OrderResult:
    return OrderResult(
        order_id=str(uuid.uuid4()),
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        qty=order.qty,
        price=price,
        status="rejected",
        filled_at=None,
        reason=reason,
    )
