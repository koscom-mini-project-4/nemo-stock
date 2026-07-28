"""조건 내장 지표 노드(12종) 단위 테스트: 계산 + 조건 판정에 따른 종목 필터링."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.market_data.base import Bar, MarketDataProvider, OrderBook, PriceTick
from app.nodes import load_all_nodes
from app.nodes.base import NodeContext, create_node

load_all_nodes()


class StubMarketData(MarketDataProvider):
    """종목별로 미리 지정한 종가 시퀀스로 일봉을 생성하는 테스트용 provider."""

    def __init__(
        self,
        closes_by_symbol: dict[str, list[float]],
        volumes_by_symbol: dict[str, list[float]] | None = None,
    ):
        self._closes = closes_by_symbol
        self._volumes = volumes_by_symbol or {}

    def get_price(self, symbol: str) -> PriceTick:  # pragma: no cover - 미사용
        c = self._closes[symbol]
        return PriceTick(symbol, c[-1], c[-2] if len(c) >= 2 else c[-1], 1000, datetime.now())

    def get_orderbook(self, symbol: str) -> OrderBook:  # pragma: no cover - 미사용
        raise NotImplementedError

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        closes = self._closes[symbol]
        vols = self._volumes.get(symbol, [10000.0] * len(closes))
        base = end - timedelta(days=len(closes) - 1)
        bars: list[Bar] = []
        for i, close in enumerate(closes):
            vol = vols[i] if i < len(vols) else vols[-1]
            bars.append(
                Bar(
                    symbol=symbol,
                    trade_date=base + timedelta(days=i),
                    open=close,
                    high=close * 1.01,
                    low=close * 0.99,
                    close=close,
                    volume=int(vol),
                )
            )
        return bars


def _ctx(symbols: list[str]) -> NodeContext:
    ctx = NodeContext(run_id="r1", mode="test", timestamp=datetime(2026, 6, 30))
    for s in symbols:
        ctx.symbols[s] = {}
    return ctx


def _run(node_type: str, params: dict, market_data: MarketDataProvider, symbols: list[str]) -> NodeContext:
    node = create_node(node_type, "ind1", params)
    return node.execute(_ctx(symbols), market_data=market_data)


def test_sma_cross_up_filters_passers_only():
    up = [100.0] * 25 + [180.0]
    down = list(range(200, 174, -1))
    md = StubMarketData({"A": up, "B": [float(x) for x in down]})
    out = _run("indicator.sma", {"window": 20, "compare_to": "현재가", "condition": "상향 돌파"}, md, ["A", "B"])
    assert "A" in out.symbols
    assert "B" not in out.symbols
    assert out.symbols["A"]["sma_20"] is not None
    assert out.meta["decisions"]["ind1"]["A"]["pass"] is True
    assert out.meta["decisions"]["ind1"]["B"]["pass"] is False


def test_ema_golden_cross_records_both_lines():
    up = [100.0] * 25 + [200.0]
    md = StubMarketData({"A": up})
    out = _run(
        "indicator.ema",
        {"window": 5, "compare_to": "다른 이평선", "compare_window": 20, "condition": "상향 돌파"},
        md,
        ["A"],
    )
    assert "A" in out.symbols
    assert "ema_5" in out.symbols["A"] and "ema_20" in out.symbols["A"]


def test_macd_records_decision_either_way():
    closes = [100.0] * 30 + [float(100 + i * 3) for i in range(1, 15)]
    md = StubMarketData({"A": closes})
    out = _run(
        "indicator.macd",
        {"fast": 12, "slow": 26, "signal": 9, "compare_to": "시그널선", "condition": "상향 돌파"},
        md,
        ["A"],
    )
    assert "ind1" in out.meta["decisions"]
    assert "A" in out.meta["decisions"]["ind1"]
    if "A" in out.symbols:
        assert "macd" in out.symbols["A"]


def test_rsi_signal_oversold_cross_down():
    closes = [float(i) for i in range(10, 40)] + [39.0 - 1.2 * i for i in range(15)]
    md = StubMarketData({"A": closes})
    out = _run("indicator.rsi_signal", {"window": 14, "threshold": 30, "condition": "하향 돌파"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["rsi_14"] < 30

    out2 = _run("indicator.rsi_signal", {"window": 14, "threshold": 30, "condition": "미만"}, md, ["A"])
    assert "A" in out2.symbols


def test_period_return_threshold():
    closes = [100.0, 101, 102, 103, 104, 110]
    md = StubMarketData({"A": closes})
    out = _run("indicator.period_return", {"window": 5, "threshold": 5, "condition": "이상"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["ret_5"] > 5

    out2 = _run("indicator.period_return", {"window": 5, "threshold": 5, "condition": "이하"}, md, ["A"])
    assert "A" not in out2.symbols
    assert out2.meta["decisions"]["ind1"]["A"]["pass"] is False


def test_volatility_below_threshold():
    closes = [100.0 + (0.01 if i % 2 == 0 else -0.01) for i in range(60)]
    md = StubMarketData({"A": closes})
    out = _run("indicator.volatility", {"window": 20, "threshold": 15, "condition": "이하"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["vol_20"] is not None


def test_bollinger_lower_touch():
    closes = [100.0] * 22 + [80.0]
    md = StubMarketData({"A": closes})
    out = _run("indicator.bollinger", {"window": 20, "num_std": 2, "band": "하단선", "condition": "터치"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["bb_lower"] is not None


class _FixedRangeMarketData(MarketDataProvider):
    """고/저/종가를 독립적으로 지정할 수 있는 테스트용 provider(ATR 계산에 필요)."""

    def __init__(self, highs: list[float], lows: list[float], closes: list[float]):
        self._highs = highs
        self._lows = lows
        self._closes = closes

    def get_price(self, symbol: str) -> PriceTick:  # pragma: no cover - 미사용
        raise NotImplementedError

    def get_orderbook(self, symbol: str) -> OrderBook:  # pragma: no cover - 미사용
        raise NotImplementedError

    def get_ohlcv(self, symbol: str, start: date, end: date) -> list[Bar]:
        base = end - timedelta(days=len(self._closes) - 1)
        return [
            Bar(
                symbol=symbol,
                trade_date=base + timedelta(days=i),
                open=c,
                high=self._highs[i],
                low=self._lows[i],
                close=c,
                volume=10000,
            )
            for i, c in enumerate(self._closes)
        ]


def test_atr_stop_breach():
    highs = [110.0] * 30
    lows = [90.0] * 30
    closes = [100.0] * 25 + [50.0] * 5  # 마지막 급락으로 추적손절선 하향 이탈 가능성
    md = _FixedRangeMarketData(highs, lows, closes)
    out = _run(
        "indicator.atr_stop", {"window": 14, "high_window": 20, "multiplier": 2, "condition": "하향 돌파"}, md, ["A"]
    )
    assert "ind1" in out.meta["decisions"]
    assert "A" in out.meta["decisions"]["ind1"]


def test_high_52w_within_range():
    closes = [100.0] * 250 + [98.0]
    md = StubMarketData({"A": closes})
    out = _run("indicator.high_52w", {"window_days": 252, "threshold": -5, "condition": "이내"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["dist_from_high_pct"] is not None


def test_mdd_exceed():
    closes = [100.0, 120, 90]
    md = StubMarketData({"A": closes})
    out = _run("indicator.mdd", {"window_days": 20, "threshold": 10, "condition": "초과"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["mdd_20"] > 10


def test_volume_ratio_spike():
    closes = [100.0] * 25
    vols = [10000.0] * 24 + [40000.0]
    md = StubMarketData({"A": closes}, {"A": vols})
    out = _run("indicator.volume_ratio", {"window": 20, "threshold": 300, "condition": "이상"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["vol_ratio_20"] >= 300


def test_volume_zscore_spike():
    closes = [100.0] * 25
    vols = [10000.0 + (i % 3) * 10 for i in range(24)] + [90000.0]
    md = StubMarketData({"A": closes}, {"A": vols})
    out = _run("indicator.volume_zscore", {"window": 20, "threshold": 2.0, "condition": "이상"}, md, ["A"])
    assert "A" in out.symbols
    assert out.symbols["A"]["vol_z_20"] >= 2.0


def test_insufficient_data_drops_symbol_and_records_decision():
    md = StubMarketData({"A": [100.0, 101.0]})  # RSI(14) 계산 불가
    out = _run("indicator.rsi_signal", {"window": 14, "threshold": 30, "condition": "하향 돌파"}, md, ["A"])
    assert "A" not in out.symbols
    assert "ind1" in out.meta["filtered_out"]
    assert out.meta["decisions"]["ind1"]["A"]["pass"] is False
    assert "탈락" in out.meta["decisions"]["ind1"]["A"]["reason"]
