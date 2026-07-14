"""주문 실행 제공자 인터페이스 (증권사 계좌 연동 추상화)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["filled", "rejected", "pending", "canceled"]


@dataclass
class OrderRequest:
    run_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: int
    limit_price: float | None = None
    ref_price: float | None = None
    """시장가 주문 시 더미/백테스트 체결가 산정에 사용하는 참조가(현재가).
    실제 증권사 어댑터는 이 값을 무시하고 실제 체결가를 반환한다."""


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: int
    price: float
    status: OrderStatus
    filled_at: datetime | None
    reason: str | None = None


@dataclass
class Position:
    symbol: str
    qty: int
    avg_price: float


@dataclass
class Balance:
    cash: float
    equity: float


class OrderExecutionProvider(ABC):
    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None: ...

    @abstractmethod
    def get_balance(self) -> Balance: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...
