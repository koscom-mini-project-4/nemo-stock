"""모멘텀(N일 전 대비 수익률) 지표 노드."""

from __future__ import annotations

from datetime import timedelta

from app.market_data.base import MarketDataProvider
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class MomentumNode(Node):
    type = "indicator.momentum"
    category = "indicator"
    display_name = "모멘텀"
    description = (
        "종목별로 params.period 거래일 전 종가 대비 현재 종가의 수익률을 계산한다("
        "예: period=20 -> 20거래일 전 대비 수익률). 입력: symbols의 종목코드 키. 출력: "
        "symbols[code]에 'momentum_{period}' 키(0.02=2% 상승처럼 소수 비율)로 값을 채운다. "
        "logic.rank 노드와 조합하면 상승률 상위 종목만 골라내는 횡단면 모멘텀 전략을 만들 수 있다. "
        "데이터가 부족하면 0.0으로 채운다."
    )
    param_schema: list[NodeParam] = [
        {"key": "period", "type": "number", "label": "기간(거래일)", "default": 20, "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider):
            raise RuntimeError("indicator.momentum 노드 실행에는 market_data provider가 필요합니다.")

        period = int(self.get_param("period", 20))
        end = context.timestamp.date()
        start = end - timedelta(days=period * 3)

        out = context.clone()
        key = f"momentum_{period}"
        for symbol in list(out.symbols.keys()):
            bars = market_data.get_ohlcv(symbol, start, end)
            closes = [b.close for b in bars]
            if len(closes) < period + 1:
                out.symbols[symbol][key] = 0.0
                continue
            past, now = closes[-(period + 1)], closes[-1]
            out.symbols[symbol][key] = round((now - past) / past, 4) if past else 0.0
        return out
