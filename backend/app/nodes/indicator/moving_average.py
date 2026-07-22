"""이동평균 지표 노드."""

from __future__ import annotations

from datetime import date, timedelta

from app.market_data.base import MarketDataProvider
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class MovingAverageNode(Node):
    type = "indicator.moving_average"
    category = "indicator"
    display_name = "이동평균"
    description = (
        "종목별로 최근 params.window일간 종가의 단순 이동평균을 계산한다. 입력: symbols의 "
        "종목코드 키(OHLCV는 market_data provider에서 직접 조회). 출력: symbols[code]에 "
        "'ma_{window}' 키(예: window=5 -> ma_5)로 평균값을 채운다."
    )
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 5, "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider):
            raise RuntimeError("indicator.moving_average 노드 실행에는 market_data provider가 필요합니다.")

        window = int(self.get_param("window", 5))
        end = context.timestamp.date()
        start = end - timedelta(days=window - 1)

        out = context.clone()
        for symbol in list(out.symbols.keys()):
            bars = market_data.get_ohlcv(symbol, start, end)
            closes = [b.close for b in bars] or [out.symbols[symbol].get("price", 0.0)]
            ma = sum(closes) / len(closes)
            out.symbols[symbol][f"ma_{window}"] = round(ma, 2)
        return out
