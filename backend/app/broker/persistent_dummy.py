"""DB로 영속화된 모의(페이퍼) 주문 실행 제공자.

DummyOrderExecutionProvider와 동일한 체결 계산(app/broker/fill_logic.py::apply_fill)을 쓰되,
현금/포지션을 매 주문마다 PortfolioRepository(SQLite)에서 읽고 다시 써서 서버 재시작에도 유지되는
'진짜 계좌 상태'로 동작한다. 라이브/테스트 실행(컨테이너 싱글턴 broker)에서 사용하고, 백테스트는
독립적인 DummyOrderExecutionProvider(인메모리)를 계속 사용한다(DESIGN.md §8-2).
"""

from __future__ import annotations

from app.broker.base import Balance, OrderExecutionProvider, OrderRequest, OrderResult, Position
from app.broker.fill_logic import apply_fill
from app.dao.base import PortfolioRepository


class PersistentOrderExecutionProvider(OrderExecutionProvider):
    def __init__(
        self, portfolio_repo: PortfolioRepository, user_id: str, default_initial_cash: float = 10_000_000.0
    ) -> None:
        self._repo = portfolio_repo
        self._user_id = user_id
        if self._repo.get_cash(user_id) is None:
            self._repo.set_cash(user_id, default_initial_cash)

    def place_order(self, order: OrderRequest) -> OrderResult:
        fill_price = order.limit_price or order.ref_price
        cash = self._repo.get_cash(self._user_id) or 0.0
        position = self._find_position(order.symbol)
        new_cash, new_position, result = apply_fill(cash, position, order, fill_price)
        if result.status == "filled":
            self._repo.set_cash(self._user_id, new_cash)
            self._repo.upsert_position(self._user_id, new_position.symbol, new_position.qty, new_position.avg_price)
        return result

    def cancel_order(self, order_id: str) -> None:
        return None

    def get_balance(self) -> Balance:
        cash = self._repo.get_cash(self._user_id) or 0.0
        equity = cash + sum(p.qty * p.avg_price for p in self._repo.list_positions(self._user_id))
        return Balance(cash=cash, equity=equity)

    def get_positions(self) -> list[Position]:
        return [
            Position(p.symbol, p.qty, p.avg_price)
            for p in self._repo.list_positions(self._user_id)
            if p.qty > 0
        ]

    def _find_position(self, symbol: str) -> Position:
        for p in self._repo.list_positions(self._user_id):
            if p.symbol == symbol:
                return Position(p.symbol, p.qty, p.avg_price)
        return Position(symbol, 0, 0.0)
