"""더미 시세 제공자.

sqlite에 적재된 최근 종가를 시드로 삼아 초 단위 랜덤워크로 현재가를 생성한다.
아직 종가 데이터가 없는 종목은 base_price(기본 5만원)에서 시작한다.
동일 seed로 생성하면 테스트에서 결정적 결과를 얻을 수 있다.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from app.market_data.base import Bar, MarketDataProvider, OrderBook, OrderBookLevel, PriceTick

DEFAULT_BASE_PRICE = 50_000.0


class DummyMarketDataProvider(MarketDataProvider):
    def __init__(
        self,
        seed_prices: dict[str, float] | None = None,
        seed: int | None = 42,
        volatility: float = 0.003,
    ) -> None:
        self._seed_prices = seed_prices or {}
        self._rng_seed = seed
        self._volatility = volatility
        self._current_prices: dict[str, float] = {}
        self._rngs: dict[str, random.Random] = {}

    def _rng_for(self, symbol: str) -> random.Random:
        if symbol not in self._rngs:
            seed = None if self._rng_seed is None else hash((self._rng_seed, symbol)) & 0xFFFFFFFF
            self._rngs[symbol] = random.Random(seed)
        return self._rngs[symbol]

    def _base_price(self, symbol: str) -> float:
        return self._seed_prices.get(symbol, DEFAULT_BASE_PRICE)

    def get_price(self, symbol: str) -> PriceTick:
        prev = self._current_prices.get(symbol, self._base_price(symbol))
        rng = self._rng_for(symbol)
        drift = rng.uniform(-self._volatility, self._volatility)
        price = max(prev * (1 + drift), 1.0)
        self._current_prices[symbol] = price
        volume = rng.randint(1_000, 50_000)
        return PriceTick(
            symbol=symbol,
            price=round(price, 1),
            prev_close=self._base_price(symbol),
            volume=volume,
            timestamp=datetime.now(),
        )

    def get_orderbook(self, symbol: str) -> OrderBook:
        tick = self.get_price(symbol)
        spread = max(tick.price * 0.001, 1.0)
        bids = [OrderBookLevel(price=round(tick.price - spread * i, 1), qty=100 * i) for i in range(1, 4)]
        asks = [OrderBookLevel(price=round(tick.price + spread * i, 1), qty=100 * i) for i in range(1, 4)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=tick.timestamp)

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        bars: list[Bar] = []
        rng = self._rng_for(symbol)
        price = self._base_price(symbol)
        current = start
        while current <= end:
            open_ = price
            drift = rng.uniform(-self._volatility * 3, self._volatility * 3)
            close = max(open_ * (1 + drift), 1.0)
            high = max(open_, close) * (1 + abs(drift) / 2)
            low = min(open_, close) * (1 - abs(drift) / 2)
            volume = rng.randint(10_000, 500_000)
            bars.append(
                Bar(
                    symbol=symbol,
                    trade_date=current,
                    open=round(open_, 1),
                    high=round(high, 1),
                    low=round(low, 1),
                    close=round(close, 1),
                    volume=volume,
                )
            )
            price = close
            current += timedelta(days=1)
        return bars
