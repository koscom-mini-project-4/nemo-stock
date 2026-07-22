"""더미(모의) 주문 실행 제공자.

현재가에 즉시 체결되는 것으로 가정하는 순수 인메모리 페이퍼 트레이딩 원장. 백테스트 전용으로
쓰인다(백테스트마다 새로 생성되어 initial_cash에서 독립적으로 시작 — DESIGN.md §0-2).
라이브/테스트 실행은 DB에 영속화되는 app/broker/persistent_dummy.py::PersistentOrderExecutionProvider
를 사용한다. 체결 계산 자체는 두 구현이 app/broker/fill_logic.py::apply_fill()을 공유한다.
"""

from __future__ import annotations

from app.broker.base import Balance, OrderExecutionProvider, OrderRequest, OrderResult, Position
from app.broker.fill_logic import apply_fill


class DummyOrderExecutionProvider(OrderExecutionProvider):
    def __init__(self, initial_cash: float = 10_000_000.0) -> None:
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: list[OrderResult] = []

    def place_order(self, order: OrderRequest) -> OrderResult:
        fill_price = order.limit_price or order.ref_price
        position = self._positions.get(order.symbol, Position(order.symbol, 0, 0.0))
        self._cash, new_position, result = apply_fill(self._cash, position, order, fill_price)
        if result.status == "filled":
            self._positions[order.symbol] = new_position
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
