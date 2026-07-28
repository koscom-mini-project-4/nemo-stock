"""지표 노드 공통 베이스.

설계: 각 지표 노드는 [계산용 파라미터]로 값을 계산하고, [매매 조건]으로 판단하여
조건을 만족하는 종목만 다음 노드로 통과시킨다(기존 logic.if_else의 필터링을 지표에 내장) —
사용자가 연산자/수식을 직접 몰라도 드롭다운에서 조건을 고르는 것만으로 매매 로직을 완성할 수 있다.

서브클래스는 compute()만 구현한다:
  - 종목의 과거 봉(bars)과 현재 심볼 데이터를 받아 IndicatorSignal을 반환.
  - IndicatorSignal은 저장할 지표값(metrics)과 조건 판정용 좌/우 값(left/right, 각각 직전·현재)을 담는다.

베이스는 아래를 공통 처리한다:
  1) market_data provider 확인 + 종목별 과거 봉 조회(lookback)
  2) compute() 호출 → metrics를 심볼 데이터에 기록
  3) 선택한 condition(연산자)으로 좌/우 값 비교 → 통과/탈락 판정
  4) 통과 종목만 남기고, 탈락 종목은 meta.filtered_out에 기록
  5) 종목별 판정 근거(값/연산자/통과여부)를 meta.decisions에 기록 — "테스트 실행" 디버그
     패널이 이 값을 읽어 노드별 판단 결과를 사람이 읽을 수 있게 보여준다(다른 필터형 노드인
     logic.if_else/logic.rank/risk.stop_loss와 동일한 포맷을 공유).
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from typing import ClassVar

from app.market_data.base import MarketDataProvider
from app.nodes.base import Node, NodeContext, NodeParam


@dataclass
class Cmp:
    """조건 판정용 값 한 쌍(직전 봉, 현재 봉). 돌파(cross) 판정에 직전값을 사용한다."""

    now: float | None
    prev: float | None = None


@dataclass
class IndicatorSignal:
    metrics: dict[str, float | None] = field(default_factory=dict)
    left: Cmp = field(default_factory=lambda: Cmp(None))
    right: Cmp = field(default_factory=lambda: Cmp(None))


# 조건(연산자) 라벨 → 판정 로직. 프론트 select에는 각 지표가 필요한 라벨만 노출한다.
def evaluate_condition(op: str, left: Cmp, right: Cmp, touch_tol: float = 0.001) -> bool:
    ln, rn = left.now, right.now
    if ln is None or rn is None:
        return False
    if op in ("크다", "초과"):
        return ln > rn
    if op in ("작다", "미만"):
        return ln < rn
    if op == "이상":
        return ln >= rn
    if op == "이하":
        return ln <= rn
    if op in ("이내",):  # |좌| 가 기준 이내(가격이 기준선 근처/위로 접근) → 좌 >= 우
        return ln >= rn
    if op in ("이탈",):
        return ln < rn
    lp, rp = left.prev, right.prev
    if op == "상향 돌파":
        if lp is None or rp is None:
            return False
        return lp <= rp and ln > rn
    if op == "하향 돌파":
        if lp is None or rp is None:
            return False
        return lp >= rp and ln < rn
    if op == "터치":
        if lp is not None and rp is not None and (lp - rp) * (ln - rn) <= 0:
            return True  # 직전 대비 부호가 바뀜 = 교차(터치)
        return abs(ln - rn) <= abs(rn) * touch_tol
    raise ValueError(f"알 수 없는 조건 연산자: {op}")


def _describe_decision(condition: str, signal: IndicatorSignal, ok: bool) -> str:
    """판단 로그용 사람이 읽는 사유 문장."""
    ln, rn = signal.left.now, signal.right.now
    if ln is None or rn is None:
        return "값 없음(데이터 부족) → 탈락"
    return f"{round(ln, 4)} {condition} {round(rn, 4)} → {'통과' if ok else '탈락'}"


# 공통 조건 파라미터 빌더 -------------------------------------------------


def condition_param(options: list[str], default: str) -> NodeParam:
    return {
        "key": "condition",
        "type": "select",
        "label": "매매 조건",
        "default": default,
        "required": True,
        "options": options,
        "group": "condition",
    }


def threshold_param(label: str, default: float, hint: str = "") -> NodeParam:
    return {
        "key": "threshold",
        "type": "number",
        "label": label,
        "default": default,
        "required": True,
        "group": "condition",
        "hint": hint,
    }


class IndicatorNode(Node):
    category = "indicator"
    # 서브클래스가 필요 시 override. 과거 봉을 몇 캘린더일 조회할지(주말 포함 여유 포함).
    lookback_days: ClassVar[int] = 90

    def _fetch_bars(self, market_data: MarketDataProvider, symbol: str, timestamp) -> list:
        end = timestamp.date()
        start = end - timedelta(days=self.lookback_days)
        return market_data.get_ohlcv(symbol, start, end)

    @abstractmethod
    def compute(self, symbol: str, bars: list, data: dict) -> IndicatorSignal:
        """과거 봉과 현재 심볼 데이터로 지표값·조건 좌우값을 계산한다."""

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        market_data = providers.get("market_data")
        if not isinstance(market_data, MarketDataProvider):
            raise RuntimeError(f"{self.type} 노드 실행에는 market_data provider가 필요합니다.")

        condition = str(self.get_param("condition"))
        out = context.clone()
        passed: dict[str, dict] = {}
        failed: list[str] = []
        decisions: dict[str, dict] = {}

        for symbol, data in out.symbols.items():
            try:
                bars = self._fetch_bars(market_data, symbol, context.timestamp)
                signal = self.compute(symbol, bars, data)
            except Exception as exc:  # noqa: BLE001 - 계산 실패 종목은 탈락 처리
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                failed.append(symbol)
                decisions[symbol] = {"pass": False, "reason": f"계산 오류: {exc}"}
                continue

            for key, value in signal.metrics.items():
                data[key] = round(value, 4) if isinstance(value, float) else value

            ok = evaluate_condition(condition, signal.left, signal.right)
            decisions[symbol] = {
                "pass": ok,
                "reason": _describe_decision(condition, signal, ok),
                "metrics": signal.metrics,
            }
            if ok:
                passed[symbol] = data
            else:
                failed.append(symbol)

        out.symbols = passed
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        out.meta.setdefault("decisions", {})[self.node_id] = decisions
        return out
