"""가격/거래량 데이터 노드."""

from __future__ import annotations

from app.market_data.base import MarketDataProvider
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class PriceDataNode(Node):
    type = "data.price"
    category = "data"
    display_name = "시세 데이터 조회"
    description = (
        "market_data provider에서 종목별 현재가를 조회한다. 입력: symbols의 종목코드 키. "
        "출력: symbols[code]에 price/prev_close/volume/change_pct를 채운다. 파라미터 없음."
    )
    param_schema: list[NodeParam] = []

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider):
            raise RuntimeError("data.price 노드 실행에는 market_data provider가 필요합니다.")

        out = context.clone()
        for symbol in list(out.symbols.keys()):
            tick = market_data.get_price(symbol)
            out.symbols[symbol].update(
                {
                    "price": tick.price,
                    "prev_close": tick.prev_close,
                    "volume": tick.volume,
                    "change_pct": round(tick.change_pct, 3),
                }
            )
        return out
