"""스칼라 신호용 '매매 조건' 프리셋 시스템.

목표: 사용자가 연산자/숫자를 직접 몰라도, 노드마다 미리 정의된 **큐레이션 프리셋**을
드롭다운에서 고르기만 하면 "살지 말지" 판단(필터)이 노드 안에서 끝나게 한다. 별도 IF 노드
없이 노드를 직렬로 이으면 AND가 된다.

- 각 노드는 `condition_presets`(사람이 읽는 라벨 + 연산자 + 기준값)를 선언한다.
- `condition_params()`가 프론트 select용 param_schema(프리셋 라벨 + '직접 설정' + 숨김 연산자/기준값)를 만든다.
- `apply_condition()`이 선택된 프리셋(또는 커스텀)으로 종목을 필터링한다(통과만 남김).

지표 노드(app/nodes/indicator/base.py)의 연산자 세트와 라벨을 공유한다(이상/이하/초과/미만).

koscom-mini-project-4/koscom_nemonemo(fork)의 뉴스 신호 파이프라인(app/nodes/data/news_signal.py,
§0-6)을 포트하며 함께 가져왔다 — 지난 조건 내장 지표 노드 작업(§0-4) 때는 이 모듈을 쓰는
노드가 없어 옮기지 않았으나, 이번엔 11개 노드가 전부 이 프리셋 시스템을 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.nodes.base import Node, NodeContext, NodeParam

# 스칼라 비교 연산자(라벨 → 판정). 지표 노드와 동일한 한국어 라벨을 쓴다.
OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "이상": lambda v, t: v >= t,
    "이하": lambda v, t: v <= t,
    "초과": lambda v, t: v > t,
    "미만": lambda v, t: v < t,
}

CUSTOM_KEY = "custom"
PASS_KEY = "pass"  # 필터 없이 통과(값만 노출)


@dataclass(frozen=True)
class Preset:
    """큐레이션된 매매 조건 하나."""

    key: str          # 저장 값(ASCII), 예: "leader"
    label: str        # 사람이 읽는 라벨, 예: "주도 섹터 (모멘텀 ≥ 0.5)"
    operator: str     # OPERATORS 키
    threshold: float
    field: str | None = None  # 판정 대상 필드 override(없으면 노드 기본 필드)


# 모든 조건 노드가 공유하는 '필터 없이 통과' 프리셋.
PASS_PRESET = Preset(PASS_KEY, "필터 없이 통과(값만 노출)", "이상", float("-inf"))


def condition_params(presets: list[Preset], default_key: str) -> list[NodeParam]:
    """프리셋 select + (커스텀 선택 시 노출되는) 연산자/기준값 파라미터를 만든다."""
    keys = [p.key for p in presets] + [CUSTOM_KEY]
    labels = [p.label for p in presets] + ["직접 설정(연산자·기준값 입력)"]
    return [
        {
            "key": "condition",
            "type": "select",
            "label": "매매 조건",
            "default": default_key,
            "required": False,  # 항상 default가 있으므로 미입력이어도 유효(default 사용)
            "group": "condition",
            "options": keys,
            "option_labels": labels,
            "hint": "이 노드가 언제 종목을 통과시킬지 고르세요",
        },
        {
            "key": "operator",
            "type": "select",
            "label": "연산자",
            "default": "이상",
            "group": "condition",
            "options": list(OPERATORS.keys()),
            "show_if": {"param": "condition", "equals": CUSTOM_KEY},
        },
        {
            "key": "threshold",
            "type": "number",
            "label": "기준값",
            "default": 0,
            "group": "condition",
            "show_if": {"param": "condition", "equals": CUSTOM_KEY},
        },
    ]


def resolve_condition(
    node: Node, presets: list[Preset], default_field: str
) -> tuple[str, float, str] | None:
    """선택된 조건을 (연산자, 기준값, 대상필드)로 해석한다. 통과(pass) 프리셋이면 None."""
    cond = str(node.get_param("condition"))
    if cond == PASS_KEY:
        return None
    if cond == CUSTOM_KEY:
        op = str(node.get_param("operator", "이상"))
        if op not in OPERATORS:
            op = "이상"
        return op, float(node.get_param("threshold", 0) or 0), default_field
    by_key = {p.key: p for p in presets}
    p = by_key.get(cond)
    if p is None:  # 알 수 없는 값 → 통과로 간주(안전)
        return None
    return p.operator, p.threshold, (p.field or default_field)


def apply_condition(
    node: Node,
    out: NodeContext,
    presets: list[Preset],
    default_field: str,
    note_fn: Callable[[dict], str] | None = None,
) -> None:
    """선택된 조건으로 종목을 필터링한다(통과만 남기고 탈락은 meta.filtered_out에 기록).

    값이 None(신호 없음)이면 보수적으로 탈락. pass 프리셋이면 필터링하지 않는다.

    nemo-stock 통합 수정: fork 원본은 meta.filtered_out/meta.conditions에만 기록했는데,
    우리 저장소는 모든 필터형 노드가 meta.decisions[node_id][symbol] = {"pass", "reason",
    "metrics"} 공통 포맷으로 판단 근거를 남기는 컨벤션이 있어(§0-4, indicator/base.py와 동일)
    이 함수도 meta.decisions를 함께 채우도록 했다 — "테스트 실행" 디버그 패널이 그 값을 읽는다.

    note_fn(§0-9): 종목 데이터(data)를 받아 reason 끝에 덧붙일 근거 문구를 돌려주는 선택적
    콜백(예: "어떤 뉴스가 이 점수를 만들었는지"). None을 돌려주면 아무것도 덧붙이지 않는다.
    생략하면(기본값) 기존과 동일하게 동작한다(하위호환).
    """
    resolved = resolve_condition(node, presets, default_field)
    if resolved is None:
        return
    op, threshold, field = resolved
    fn = OPERATORS[op]
    passed: dict[str, dict] = {}
    failed: list[str] = []
    detail: dict[str, dict] = {}
    decisions: dict[str, dict] = {}
    for symbol, data in out.symbols.items():
        value = data.get(field)
        ok = value is not None and fn(float(value), threshold)
        detail[symbol] = {"field": field, "value": value, "op": op, "threshold": threshold, "pass": ok}
        reason = (
            f"{field}={value} {op} {threshold} → {'통과' if ok else '탈락'}"
            if value is not None
            else f"{field} 값 없음(데이터 부족) → 탈락"
        )
        note = note_fn(data) if note_fn else None
        if note:
            reason += f" | {note}"
        decisions[symbol] = {"pass": ok, "reason": reason, "metrics": {"field": field, "value": value}}
        if ok:
            passed[symbol] = data
        else:
            failed.append(symbol)
    out.symbols = passed
    out.meta.setdefault("filtered_out", {})[node.node_id] = failed
    out.meta.setdefault("conditions", {})[node.node_id] = detail
    out.meta.setdefault("decisions", {})[node.node_id] = decisions
