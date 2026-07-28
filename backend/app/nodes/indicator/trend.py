"""추세 지표(조건 내장): SMA / EMA / MACD.

기존 indicator.moving_average(값만 계산)와 달리, 여기 노드들은 계산+조건 판정까지
자체 완결하는 필터형 노드다(logic.if_else 없이 이 노드 하나로 "이평선 돌파 시 매수" 같은
전략을 만들 수 있음).
"""

from __future__ import annotations

from app.nodes.base import NodeParam, register_node
from app.nodes.indicator import calc
from app.nodes.indicator.base import Cmp, IndicatorNode, IndicatorSignal, condition_param


def _closes(bars: list) -> list[float]:
    return [b.close for b in bars]


@register_node
class SmaNode(IndicatorNode):
    type = "indicator.sma"
    subcategory = "추세"
    display_name = "단순이동평균 (SMA)"
    description = (
        "종목별 params.window일 종가 단순이동평균을 계산해 symbols[code]에 'sma_{window}'로 "
        "채운다. params.compare_to(현재가 또는 다른 이평선)와 params.condition(크다/작다/상향 "
        "돌파/하향 돌파)으로 판정해 조건을 만족하는 종목만 통과시키는 필터형 노드다(logic.if_else "
        "내장). 통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "현재가가 20일 SMA를 상향 돌파할 때"
    lookback_days = 320
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 20, "required": True,
         "group": "calc", "hint": "5, 20, 60, 120"},
        {"key": "compare_to", "type": "select", "label": "비교 대상", "default": "현재가",
         "required": True, "options": ["현재가", "다른 이평선"], "group": "condition"},
        {"key": "compare_window", "type": "number", "label": "비교 이평선 기간(일)", "default": 60,
         "required": False, "group": "condition", "hint": "비교 대상=다른 이평선 일 때 사용"},
        condition_param(["크다", "작다", "상향 돌파", "하향 돌파"], "상향 돌파"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = _closes(bars)
        window = int(self.get_param("window", 20))
        sma = calc.sma_series(closes, window)
        metrics: dict[str, float | None] = {f"sma_{window}": sma[-1] if sma else None}

        if str(self.get_param("compare_to", "현재가")) == "현재가":
            left = Cmp(now=closes[-1] if closes else None, prev=closes[-2] if len(closes) >= 2 else None)
            right = Cmp(now=sma[-1], prev=sma[-2] if len(sma) >= 2 else None)
        else:
            cw = int(self.get_param("compare_window", 60))
            sma_c = calc.sma_series(closes, cw)
            metrics[f"sma_{cw}"] = sma_c[-1] if sma_c else None
            left = Cmp(now=sma[-1], prev=sma[-2] if len(sma) >= 2 else None)
            right = Cmp(now=sma_c[-1], prev=sma_c[-2] if len(sma_c) >= 2 else None)
        return IndicatorSignal(metrics=metrics, left=left, right=right)


@register_node
class EmaNode(IndicatorNode):
    type = "indicator.ema"
    subcategory = "추세"
    display_name = "지수이동평균 (EMA)"
    description = (
        "종목별 params.window일 지수이동평균(최근 가격에 가중치를 더 준 이평선)을 계산해 "
        "symbols[code]에 'ema_{window}'로 채운다. params.compare_to(현재가 또는 다른 이평선)와 "
        "params.condition으로 골든/데드크로스를 판정하는 필터형 노드(logic.if_else 내장). "
        "통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "5일 EMA가 20일 EMA를 상향 돌파할 때 (골든크로스)"
    lookback_days = 320
    param_schema: list[NodeParam] = [
        {"key": "window", "type": "number", "label": "기간(일)", "default": 5, "required": True,
         "group": "calc", "hint": "빠른 이평선 기간"},
        {"key": "compare_to", "type": "select", "label": "비교 대상", "default": "다른 이평선",
         "required": True, "options": ["현재가", "다른 이평선"], "group": "condition"},
        {"key": "compare_window", "type": "number", "label": "비교 이평선 기간(일)", "default": 20,
         "required": False, "group": "condition", "hint": "느린 이평선 기간"},
        condition_param(["크다", "작다", "상향 돌파", "하향 돌파"], "상향 돌파"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = _closes(bars)
        window = int(self.get_param("window", 5))
        ema = calc.ema_series(closes, window)
        metrics: dict[str, float | None] = {f"ema_{window}": ema[-1] if ema else None}

        if str(self.get_param("compare_to", "다른 이평선")) == "현재가":
            left = Cmp(now=closes[-1] if closes else None, prev=closes[-2] if len(closes) >= 2 else None)
            right = Cmp(now=ema[-1], prev=ema[-2] if len(ema) >= 2 else None)
        else:
            cw = int(self.get_param("compare_window", 20))
            ema_c = calc.ema_series(closes, cw)
            metrics[f"ema_{cw}"] = ema_c[-1] if ema_c else None
            left = Cmp(now=ema[-1], prev=ema[-2] if len(ema) >= 2 else None)
            right = Cmp(now=ema_c[-1], prev=ema_c[-2] if len(ema_c) >= 2 else None)
        return IndicatorSignal(metrics=metrics, left=left, right=right)


@register_node
class MacdNode(IndicatorNode):
    type = "indicator.macd"
    subcategory = "추세"
    display_name = "MACD"
    description = (
        "종목별로 params.fast/slow EMA 차이(MACD선)와 params.signal 기간의 시그널선을 계산해 "
        "symbols[code]에 'macd'/'macd_sig'/'macd_hist'로 채운다. params.compare_to(시그널선 또는 "
        "0선)와 params.condition으로 추세 전환을 판정하는 필터형 노드(logic.if_else 내장). "
        "통과/탈락 근거는 meta.decisions에 기록된다."
    )
    example = "MACD선이 시그널선을 상향 돌파할 때"
    lookback_days = 400
    param_schema: list[NodeParam] = [
        {"key": "fast", "type": "number", "label": "빠른 기간", "default": 12, "required": True, "group": "calc"},
        {"key": "slow", "type": "number", "label": "느린 기간", "default": 26, "required": True, "group": "calc"},
        {"key": "signal", "type": "number", "label": "시그널 기간", "default": 9, "required": True, "group": "calc"},
        {"key": "compare_to", "type": "select", "label": "비교 대상", "default": "시그널선",
         "required": True, "options": ["시그널선", "0선"], "group": "condition"},
        condition_param(["크다", "작다", "상향 돌파", "하향 돌파"], "상향 돌파"),
    ]

    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        closes = _closes(bars)
        fast = int(self.get_param("fast", 12))
        slow = int(self.get_param("slow", 26))
        signal = int(self.get_param("signal", 9))
        macd_line, signal_line, hist = calc.macd_series(closes, fast, slow, signal)
        metrics = {
            "macd": macd_line[-1] if macd_line else None,
            "macd_sig": signal_line[-1] if signal_line else None,
            "macd_hist": hist[-1] if hist else None,
        }
        left = Cmp(now=macd_line[-1], prev=macd_line[-2] if len(macd_line) >= 2 else None)
        if str(self.get_param("compare_to", "시그널선")) == "시그널선":
            right = Cmp(now=signal_line[-1], prev=signal_line[-2] if len(signal_line) >= 2 else None)
        else:
            right = Cmp(now=0.0, prev=0.0)
        return IndicatorSignal(metrics=metrics, left=left, right=right)
