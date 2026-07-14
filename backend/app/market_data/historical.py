"""과거 일봉 리플레이 기반 시세 제공자 (백테스트 전용).

PriceBarRepository에 적재된 sqlite price_bars를 날짜 커서 기준으로 리플레이한다.
BacktestRunner가 매 거래일마다 advance_to(date)를 호출해 커서를 이동시킨 뒤
WorkflowEngine.execute()가 get_price/get_ohlcv를 호출하는 방식으로 동작한다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.dao.base import PriceBarRepository
from app.market_data.base import Bar, MarketDataProvider, OrderBook, OrderBookLevel, PriceTick


class HistoricalMarketDataProvider(MarketDataProvider):
    def __init__(self, price_bar_repo: PriceBarRepository, universe: list[str], lookback_days: int = 400) -> None:
        self._repo = price_bar_repo
        self._universe = universe
        self._lookback_days = lookback_days
        self._current_date: date | None = None
        self._cache: dict[str, list] = {}

    def advance_to(self, trade_date: date) -> None:
        self._current_date = trade_date
        self._cache = {}

    def _bars_up_to_current(self, symbol: str):
        if self._current_date is None:
            raise RuntimeError("advance_to(date)로 리플레이 기준일을 먼저 설정해야 합니다.")
        if symbol not in self._cache:
            start = self._current_date - timedelta(days=self._lookback_days)
            self._cache[symbol] = self._repo.list_range(symbol, start, self._current_date)
        return self._cache[symbol]

    def get_price(self, symbol: str) -> PriceTick:
        bars = self._bars_up_to_current(symbol)
        if not bars:
            raise RuntimeError(f"{symbol}의 {self._current_date} 이전 시세 데이터가 없습니다.")
        latest = bars[-1]
        prev_close = bars[-2].close if len(bars) >= 2 else latest.open
        return PriceTick(
            symbol=symbol,
            price=latest.close,
            prev_close=prev_close,
            volume=latest.volume,
            timestamp=datetime.combine(latest.trade_date, time()),
        )

    def get_orderbook(self, symbol: str) -> OrderBook:
        tick = self.get_price(symbol)
        spread = max(tick.price * 0.001, 1.0)
        bids = [OrderBookLevel(price=round(tick.price - spread * i, 1), qty=100 * i) for i in range(1, 4)]
        asks = [OrderBookLevel(price=round(tick.price + spread * i, 1), qty=100 * i) for i in range(1, 4)]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=tick.timestamp)

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        records = self._repo.list_range(symbol, start, end)
        return [
            Bar(symbol=symbol, trade_date=r.trade_date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
            for r in records
        ]
