"""위험 지표(조건 내장): 최대낙폭(MDD).

app/nodes/risk/(손절·비중 제한 등 리스크 관리 노드) 패키지와는 별개다. 이 노드는
"조회 기간 내 가격만으로 계산되는" 지표형 MDD이며, 카테고리는 indicator다.
"""

from __future__ import annotations

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator import calc
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param, threshold_param


@register_node
class MddNode(IndicatorNode):
    type = "indicator.mdd"
    subcategory = "위험"
    display_name = "최대낙폭 (MDD)"
    description = (
        "종목별 params.window_days거래일 내 고점 대비 최대 하락폭(%, 양수 크기)을 계산해 "
        "symbols[code]에 'mdd_{window_days}'로 채운다. params.threshold와 params.condition(초과/"
        "이하)으로 한계 낙폭 초과 여부를 판정하는 필터형 노드다(logic.if_else 내장, 예: 시스템 "
        "강제 종료 조건). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "현재 MDD가 10%를 초과할 때 (시스템 강제 종료)"
    lookback_days = 200
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "조회 기간(거래일)", "default": 20,
         "required": True, "group": "calc"},
        threshold_param("한계 낙폭(%)", 10, hint="양수 크기. 예: 10 = -10%"),
        condition_param(["초과", "이하"], "초과"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = [b.close for b in bars]
        window = int(self.get_param("window_days", 20))
        threshold = float(self.get_param("threshold", 10))
        if not closes:
            return IndicatorSignal(metrics={f"mdd_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        mdd = calc.max_drawdown_pct(closes[-window:])
        return IndicatorSignal(metrics={f"mdd_{window}": mdd}, left=Cmp(now=mdd), right=Cmp(now=threshold))
