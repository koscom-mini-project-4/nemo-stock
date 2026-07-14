"""더미(모의) 주문 실행 제공자.

현재가에 즉시 체결되는 것으로 가정하는 페이퍼 트레이딩 원장.
테스트/백테스트 공용으로 사용한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.broker.base import Balance, OrderExecutionProvider, OrderRequest, OrderResult, Position


class DummyOrderExecutionProvider(OrderExecutionProvider):
    def __init__(self, initial_cash: float = 10_000_000.0) -> None:
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: list[OrderResult] = []

    def place_order(self, order: OrderRequest) -> OrderResult:
        fill_price = order.limit_price or order.ref_price
        if fill_price is None:
            result = OrderResult(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                price=0.0,
                status="rejected",
                filled_at=None,
                reason="체결 기준가(ref_price/limit_price)가 없습니다.",
            )
            self._orders.append(result)
            return result

        cost = fill_price * order.qty
        if order.side == "buy":
            if cost > self._cash:
                result = OrderResult(
                    order_id=str(uuid.uuid4()),
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    qty=order.qty,
                    price=fill_price,
                    status="rejected",
                    filled_at=None,
                    reason="잔고 부족",
                )
                self._orders.append(result)
                return result
            self._cash -= cost
            pos = self._positions.get(order.symbol, Position(order.symbol, 0, 0.0))
            new_qty = pos.qty + order.qty
            new_avg = (pos.avg_price * pos.qty + cost) / new_qty if new_qty else 0.0
            self._positions[order.symbol] = Position(order.symbol, new_qty, new_avg)
        else:  # sell
            pos = self._positions.get(order.symbol, Position(order.symbol, 0, 0.0))
            if pos.qty < order.qty:
                result = OrderResult(
                    order_id=str(uuid.uuid4()),
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    qty=order.qty,
                    price=fill_price,
                    status="rejected",
                    filled_at=None,
                    reason="보유 수량 부족",
                )
                self._orders.append(result)
                return result
            realized_pnl = (fill_price - pos.avg_price) * order.qty
            self._cash += cost
            remaining = pos.qty - order.qty
            self._positions[order.symbol] = Position(order.symbol, remaining, pos.avg_price if remaining else 0.0)
            result = OrderResult(
                order_id=str(uuid.uuid4()),
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                qty=order.qty,
                price=fill_price,
                status="filled",
                filled_at=datetime.now(),
                realized_pnl=realized_pnl,
            )
            self._orders.append(result)
            return result

        result = OrderResult(
            order_id=str(uuid.uuid4()),
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            qty=order.qty,
            price=fill_price,
            status="filled",
            filled_at=datetime.now(),
        )
        self._orders.append(result)
        return result

    def cancel_order(self, order_id: str) -> None:
        # 더미 구현은 즉시 체결이므로 취소 대상이 없다.
        return None

    def get_balance(self) -> Balance:
        equity = self._cash + sum(p.qty * p.avg_price for p in self._positions.values())
        return Balance(cash=self._cash, equity=equity)

    def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.qty > 0]

    @property
    def orders(self) -> list[OrderResult]:
        return self._orders
