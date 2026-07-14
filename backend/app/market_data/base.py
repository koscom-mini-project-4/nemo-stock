"""시세 데이터 제공자 인터페이스.

실제 서비스 연동(Toss증권 등)과 PoC 더미/과거데이터 리플레이를 동일한 인터페이스로
교체 가능하게 하기 위한 추상화.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class PriceTick:
    symbol: str
    price: float
    prev_close: float
    volume: int
    timestamp: datetime

    @property
    def change_pct(self) -> float:
        if self.prev_close == 0:
            return 0.0
        return (self.price - self.prev_close) / self.prev_close * 100


@dataclass
class OrderBookLevel:
    price: float
    qty: int


@dataclass
class OrderBook:
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime


@dataclass
class Bar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketDataProvider(ABC):
    @abstractmethod
    def get_price(self, symbol: str) -> PriceTick: ...

    @abstractmethod
    def get_orderbook(self, symbol: str) -> OrderBook: ...

    @abstractmethod
    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]: ...
