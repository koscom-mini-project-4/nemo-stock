"""변동성 지표(조건 내장): 연율화 변동성 / 볼린저 밴드 / ATR 추적 손절."""

from __future__ import annotations

import math

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator import calc
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param, threshold_param

TRADING_DAYS_PER_YEAR = 252


@register_node
class VolatilityNode(IndicatorNode):
    type = "indicator.volatility"
    subcategory = "변동성"
    display_name = "연율화 변동성"
    description = (
        "종목별 params.window일 일간수익률 표준편차를 연율화(%)해 symbols[code]에 'vol_{window}'로 "
        "채운다. params.threshold와 params.condition(이상/이하)으로 변동성 축소/확대 국면을 "
        "판정하는 필터형 노드다(logic.if_else 내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "20일 변동성이 15% 이하일 때 (변동성 축소기)"
    lookback_days = 160
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 20, "required": True,
         "group": "calc", "hint": "20, 60"},
        threshold_param("기준 변동성(%)", 15),
        condition_param(["이상", "이하"], "이하"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = [b.close for b in bars]
        window = int(self.get_param("window", 20))
        threshold = float(self.get_param("threshold", 15))
        rets = calc.daily_returns(closes)
        if len(rets) < window:
            return IndicatorSignal(metrics={f"vol_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        vol = calc.stddev(rets[-window:]) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0
        return IndicatorSignal(metrics={f"vol_{window}": vol}, left=Cmp(now=vol), right=Cmp(now=threshold))


@register_node
class BollingerNode(IndicatorNode):
    type = "indicator.bollinger"
    subcategory = "변동성"
    display_name = "볼린저 밴드"
    description = (
        "종목별 params.window일 이동평균 ± params.num_std표준편차 밴드를 계산해 symbols[code]에 "
        "'bb_upper'/'bb_mid'/'bb_lower'로 채운다. params.band(상단/중심/하단선)와 params.condition"
        "(터치/상향 돌파/하향 돌파)으로 현재가와 밴드의 관계를 판정하는 필터형 노드다(logic.if_else "
        "내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "현재가가 볼린저 밴드 하단선을 터치할 때"
    lookback_days = 120
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 20, "required": True, "group": "calc"},
        {"key": "num_std", "type": "number", "label": "표준편차 배수", "default": 2, "required": True,
         "group": "calc", "hint": "보통 2"},
        {"key": "band", "type": "select", "label": "비교 대상", "default": "하단선",
         "required": True, "options": ["상단선", "중심선", "하단선"], "group": "condition"},
        condition_param(["터치", "상향 돌파", "하향 돌파"], "터치"),
    ]

    def _band_series(self, closes: list[float], window: int, num_std: float):
        mid = calc.sma_series(closes, window)
        upper: list[float | None] = [None] * len(closes)
        lower: list[float | None] = [None] * len(closes)
        for i in range(len(closes)):
            if i + 1 >= window:
                sd = calc.stddev(closes[i + 1 - window : i + 1])
                m = mid[i]
                if m is not None:
                    upper[i] = m + num_std * sd
                    lower[i] = m - num_std * sd
        return upper, mid, lower

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = [b.close for b in bars]
        window = int(self.get_param("window", 20))
        num_std = float(self.get_param("num_std", 2))
        upper, mid, lower = self._band_series(closes, window, num_std)
        metrics = {
            "bb_upper": upper[-1] if upper else None,
            "bb_mid": mid[-1] if mid else None,
            "bb_lower": lower[-1] if lower else None,
        }
        band_key = {"상단선": upper, "중심선": mid, "하단선": lower}[str(self.get_param("band", "하단선"))]
        left = Cmp(now=closes[-1] if closes else None, prev=closes[-2] if len(closes) >= 2 else None)
        right = Cmp(now=band_key[-1], prev=band_key[-2] if len(band_key) >= 2 else None)
        return IndicatorSignal(metrics=metrics, left=left, right=right)


@register_node
class AtrStopNode(IndicatorNode):
    type = "indicator.atr_stop"
    subcategory = "변동성"
    display_name = "ATR 추적 손절"
    description = (
        "종목별로 params.window일 ATR과 최근 params.high_window일 고점으로 추적 손절선(고점 - "
        "ATR×params.multiplier)을 계산해 symbols[code]에 'atr_{window}'/'atr_stop'으로 채운다. "
        "현재가가 이 선을 이탈하는지 params.condition으로 판정하는 필터형 노드다(logic.if_else "
        "내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "고점 대비 ATR의 2배만큼 하락했을 때 (Trailing Stop)"
    lookback_days = 120
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "ATR 기간(일)", "default": 14, "required": True, "group": "calc"},
        {"key": "high_window", "type": "number", "label": "고점 조회 기간(일)", "default": 20,
         "required": True, "group": "calc"},
        {"key": "multiplier", "type": "number", "label": "ATR 배수(N배)", "default": 2, "required": True,
         "group": "condition", "hint": "고점 대비 ATR N배 이탈"},
        condition_param(["하향 돌파", "상향 돌파"], "하향 돌파"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        window = int(self.get_param("window", 14))
        high_window = int(self.get_param("high_window", 20))
        mult = float(self.get_param("multiplier", 2))

        atr = calc.atr_series(highs, lows, closes, window)
        roll_high = calc.rolling_max(highs, high_window)
        stop: list[float | None] = [
            (h - mult * a) if (h is not None and a is not None) else None for h, a in zip(roll_high, atr)
        ]
        metrics = {f"atr_{window}": atr[-1] if atr else None, "atr_stop": stop[-1] if stop else None}
        left = Cmp(now=closes[-1] if closes else None, prev=closes[-2] if len(closes) >= 2 else None)
        right = Cmp(now=stop[-1], prev=stop[-2] if len(stop) >= 2 else None)
        return IndicatorSignal(metrics=metrics, left=left, right=right)
