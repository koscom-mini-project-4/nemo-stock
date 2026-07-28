"""RSI(상대강도지수) 지표 노드."""

from __future__ import annotations

from datetime import timedelta

from app.market_data.base import MarketDataProvider
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class RsiNode(Node):
    type = "indicator.rsi"
    category = "indicator"
    display_name = "RSI"
    description = (
        "종목별로 최근 params.period일간 종가로 상대강도지수(RSI, 0~100)를 계산한다. "
        "입력: symbols의 종목코드 키(OHLCV는 market_data provider에서 직접 조회). "
        "출력: symbols[code]에 'rsi_{period}' 키(예: period=14 -> rsi_14)로 값을 채운다. "
        "데이터가 부족하면(거래일 < period+1) 50.0(중립)으로 채운다."
    )
    param_schema: list[NodeParam] = [
        {"key": "period", "type": "number", "label": "기간(일)", "default": 14, "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider):
            raise RuntimeError("indicator.rsi 노드 실행에는 market_data provider가 필요합니다.")

        period = int(self.get_param("period", 14))
        end = context.timestamp.date()
        start = end - timedelta(days=period * 3)  # 주말/휴장일 여유를 두어 거래일 period+1개를 확보

        out = context.clone()
        key = f"rsi_{period}"
        for symbol in list(out.symbols.keys()):
            bars = market_data.get_ohlcv(symbol, start, end)
            closes = [b.close for b in bars]
            if len(closes) < period + 1:
                out.symbols[symbol][key] = 50.0
                continue
            window = closes[-(period + 1):]
            gains = 0.0
            losses = 0.0
            for prev, curr in zip(window, window[1:]):
                change = curr - prev
                if change >= 0:
                    gains += change
                else:
                    losses -= change
            avg_gain = gains / period
            avg_loss = losses / period
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            out.symbols[symbol][key] = round(rsi, 2)
        return out
