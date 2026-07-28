"""거래량 지표(조건 내장): 거래량 비율 / 거래량 Z-score."""

from __future__ import annotations

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator import calc
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param, threshold_param


@register_node
class VolumeRatioNode(IndicatorNode):
    type = "indicator.volume_ratio"
    subcategory = "거래량"
    display_name = "거래량 비율"
    description = (
        "종목별 오늘 거래량 ÷ params.window일 평균 거래량(%)을 계산해 symbols[code]에 "
        "'vol_ratio_{window}'로 채운다. params.threshold와 params.condition(이상/이하)으로 거래량 "
        "급증/급감을 판정하는 필터형 노드다(logic.if_else 내장). 통과/탈락 근거는 meta.decisions에 "
        "기록된다."
    )
    example = "오늘 거래량이 20일 평균 거래량의 300% 이상일 때"
    lookback_days = 90
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "평균 기간(일)", "default": 20, "required": True, "group": "calc"},
        threshold_param("기준 비율(%)", 200, hint="예: 200, 300"),
        condition_param(["이상", "이하"], "이상"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        vols = [float(b.volume) for b in bars]
        window = int(self.get_param("window", 20))
        threshold = float(self.get_param("threshold", 200))
        if len(vols) < window + 1:
            return IndicatorSignal(metrics={f"vol_ratio_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        avg = calc.mean(vols[-1 - window : -1])  # 오늘 제외 직전 window일 평균
        if avg == 0:
            return IndicatorSignal(metrics={f"vol_ratio_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        ratio = vols[-1] / avg * 100.0
        return IndicatorSignal(metrics={f"vol_ratio_{window}": ratio}, left=Cmp(now=ratio), right=Cmp(now=threshold))


@register_node
class VolumeZScoreNode(IndicatorNode):
    type = "indicator.volume_zscore"
    subcategory = "거래량"
    display_name = "거래량 Z-score"
    description = (
        "종목별 오늘 거래량이 params.window일 평균 대비 몇 표준편차인지 계산해 symbols[code]에 "
        "'vol_z_{window}'로 채운다. params.threshold와 params.condition(이상/이하)으로 통계적으로 "
        "유의미한 거래량 급증을 판정하는 필터형 노드다(logic.if_else 내장). 통과/탈락 근거는 "
        "meta.decisions에 기록된다."
    )
    example = "거래량 Z-score가 +2.0 이상일 때 (통계적 유의미한 급증)"
    lookback_days = 90
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기준 기간(일)", "default": 20, "required": True, "group": "calc"},
        threshold_param("기준 Z값", 2.0, hint="예: +2.0, +3.0"),
        condition_param(["이상", "이하"], "이상"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        vols = [float(b.volume) for b in bars]
        window = int(self.get_param("window", 20))
        threshold = float(self.get_param("threshold", 2.0))
        if len(vols) < window + 1:
            return IndicatorSignal(metrics={f"vol_z_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        base = vols[-1 - window : -1]
        mu = calc.mean(base)
        sd = calc.stddev(base)
        if sd == 0:
            return IndicatorSignal(metrics={f"vol_z_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        z = (vols[-1] - mu) / sd
        return IndicatorSignal(metrics={f"vol_z_{window}": z}, left=Cmp(now=z), right=Cmp(now=threshold))
