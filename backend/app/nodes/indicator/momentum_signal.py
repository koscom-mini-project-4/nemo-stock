"""모멘텀 지표(조건 내장): RSI 매매신호 / 기간 수익률.

기존 indicator.rsi/indicator.momentum(값만 계산, 필터링 없음)과 별개의 필터형 노드다.
RSI는 기존 노드와 타입이 겹치므로 'indicator.rsi_signal'로 구분한다(기존 워크플로가
참조하는 indicator.rsi의 동작을 바꾸지 않기 위함).
"""

from __future__ import annotations

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator import calc
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param, threshold_param


@register_node
class RsiSignalNode(IndicatorNode):
    type = "indicator.rsi_signal"
    subcategory = "모멘텀"
    display_name = "RSI 매매신호"
    description = (
        "종목별 params.window일 RSI(0~100)를 계산해 symbols[code]에 'rsi_{window}'로 채우고, "
        "params.threshold 기준값과 params.condition(초과/미만/상향 돌파/하향 돌파)으로 과매수/"
        "과매도를 판정해 조건을 만족하는 종목만 통과시키는 필터형 노드다(logic.if_else 내장). "
        "값만 계산하고 필터링하지 않는 기존 indicator.rsi와는 별개 노드다. 통과/탈락 근거는 "
        "meta.decisions에 기록된다."
    )
    example = "RSI가 30을 하향 돌파할 때 (과매도 진입)"
    lookback_days = 90
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 14, "required": True, "group": "calc"},
        threshold_param("기준 수치", 30, hint="예: 30, 70"),
        condition_param(["초과", "미만", "상향 돌파", "하향 돌파"], "하향 돌파"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = [b.close for b in bars]
        window = int(self.get_param("window", 14))
        threshold = float(self.get_param("threshold", 30))
        rsi = calc.rsi_series(closes, window)
        left = Cmp(now=rsi[-1], prev=rsi[-2] if len(rsi) >= 2 else None)
        right = Cmp(now=threshold, prev=threshold)
        return IndicatorSignal(metrics={f"rsi_{window}": rsi[-1] if rsi else None}, left=left, right=right)


@register_node
class PeriodReturnNode(IndicatorNode):
    type = "indicator.period_return"
    subcategory = "모멘텀"
    display_name = "기간 수익률"
    description = (
        "종목별 params.window거래일 전 종가 대비 현재 종가의 수익률(%)을 계산해 symbols[code]에 "
        "'ret_{window}'로 채운다. params.threshold 목표 수익률과 params.condition(이상/이하)으로 "
        "판정하는 필터형 노드다(logic.if_else 내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "5일 기간 수익률이 5% 이상일 때"
    lookback_days = 300
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 5, "required": True,
         "group": "calc", "hint": "1, 5, 20, 60, 120"},
        threshold_param("목표 수익률(%)", 5, hint="예: +5, -3"),
        condition_param(["이상", "이하"], "이상"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = [b.close for b in bars]
        window = int(self.get_param("window", 5))
        threshold = float(self.get_param("threshold", 5))
        if len(closes) <= window or closes[-1 - window] == 0:
            return IndicatorSignal(metrics={f"ret_{window}": None}, left=Cmp(None), right=Cmp(threshold))
        ret = (closes[-1] / closes[-1 - window] - 1.0) * 100.0
        return IndicatorSignal(
            metrics={f"ret_{window}": ret}, left=Cmp(now=ret), right=Cmp(now=threshold)
        )
