"""가격 위치 지표(조건 내장): 52주 최고가 대비 낙폭."""

from __future__ import annotations

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param, threshold_param


@register_node
class High52wNode(IndicatorNode):
    type = "indicator.high_52w"
    subcategory = "가격 위치"
    display_name = "52주 최고가 대비"
    description = (
        "종목별 params.window_days거래일 내 최고가 대비 현재가의 낙폭(%)을 계산해 symbols[code]에 "
        "'high_52w'/'dist_from_high_pct'로 채운다. params.threshold와 params.condition(이내/이탈/"
        "상향 돌파)으로 신고가 근접(돌파 매매)이나 이탈을 판정하는 필터형 노드다(logic.if_else "
        "내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "52주 최고가 대비 -5% 이내로 접근할 때 (돌파 매매)"
    lookback_days = 400
    param_schema: list[NodeParam] = [
        {"key": "window_days", "type": "number", "label": "조회 기간(거래일)", "default": 252,
         "required": True, "group": "calc", "hint": "52주 ≈ 252 거래일"},
        threshold_param("기준 낙폭(%)", -5, hint="예: -5 (최고가 대비 -5%)"),
        condition_param(["이내", "이탈", "상향 돌파"], "이내"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        highs = [b.high for b in bars]
        closes = [b.close for b in bars]
        window = int(self.get_param("window_days", 252))
        threshold = float(self.get_param("threshold", -5))
        if not highs:
            return IndicatorSignal(metrics={"dist_from_high_pct": None}, left=Cmp(None), right=Cmp(threshold))

        def _dist(idx: int) -> float | None:
            window_slice = highs[max(0, idx + 1 - window) : idx + 1]
            hi = max(window_slice) if window_slice else None
            if hi is None or hi == 0:
                return None
            return (closes[idx] / hi - 1.0) * 100.0

        now = _dist(len(closes) - 1)
        prev = _dist(len(closes) - 2) if len(closes) >= 2 else None
        high_now = max(highs[-window:]) if highs else None
        metrics = {"high_52w": high_now, "dist_from_high_pct": now}
        return IndicatorSignal(metrics=metrics, left=Cmp(now=now, prev=prev), right=Cmp(now=threshold, prev=threshold))
