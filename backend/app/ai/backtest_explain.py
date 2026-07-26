"""백테스트 결과 화면(매매 시점/구간)에 대한 AI 진단·수정 제안.

app/ai/workflow_chat.py::chat_about_workflow와 동일한 계약(reply/changed/name/graph/disclaimer,
changed=true일 때 WorkflowGraph.validate() 검증 + 1회 재시도)을 그대로 따른다 — 프론트가
ChatPanel.vue와 같은 "미리보기 후 적용" UI를 그대로 재사용할 수 있게 하기 위함이다.

이 모듈 자체는 저장/적용을 하지 않는다. 라우터(app/api/routers/ai.py)가 backtest_id로부터
selection(거래 내역/노드 실행 요약/시세/참고 뉴스)을 조립해 넘겨주면, 그 근거 데이터를 바탕으로
설명하거나 그래프 수정을 제안한다.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.base import AIClient
from app.nodes.base import node_registry_schema
from app.workflow.graph import WorkflowGraph

BACKTEST_EXPLAIN_DISCLAIMER = (
    "AI의 설명/수정 제안은 백테스트 근거 데이터를 참고한 분석 보조 정보이며 투자 자문이 아닙니다. "
    "수정 제안은 '전략 빌더에서 열기'로 캔버스에 불러온 뒤 직접 검토하고 저장해야 반영됩니다."
)


class BacktestExplainError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


def _build_system_prompt() -> str:
    registry = node_registry_schema()
    return (
        "당신은 노코드 주식 자동매매 전략의 백테스트 결과를 진단하는 어시스턴트입니다.\n"
        "사용자가 백테스트 그래프에서 특정 매매 시점(point) 또는 매매가 없었던 구간(range)을 선택하고 "
        "질문합니다. 함께 제공되는 근거 데이터(selection: 그 구간의 거래 내역, 노드별 실행 요약, "
        "종가 시계열, 워크플로가 실제로 참고한 뉴스)를 바탕으로 현재 워크플로 그래프의 로직이 왜 그렇게 "
        "동작했는지 설명하세요.\n\n"
        "요청 유형을 다음 두 가지로 구분하세요:\n"
        "1. 단순 설명/진단 요청 -> changed=false로 응답하고 reply에 원인을 구체적으로 설명합니다. "
        "노드 실행 요약(nodes)에서 어느 노드가 어떤 값으로 어떤 종목을 걸러냈는지/주문을 냈는지를 "
        "직접 인용해 근거를 제시하세요.\n"
        "2. 로직이 잘못됐다고 판단되거나 사용자가 특정 결과(매매 발생/차단 등)를 원해서 수정을 요청한 "
        "경우 -> changed=true로 응답하고, 그 목적을 달성하도록 수정한 전체 그래프(JSON)를 nodes/edges에 "
        "채우세요. 무관한 기존 노드/파라미터는 가능한 한 그대로 유지합니다. reply에는 무엇을, 왜 "
        "바꿨는지 한두 문장으로 한국어 요약을 담습니다.\n\n"
        "사용 가능한 노드 타입 (type, category, param_schema):\n"
        f"{json.dumps(registry, ensure_ascii=False, indent=2)}\n\n"
        "모든 종목 데이터에는 held_qty(보유수량)/held_avg_price(평단가)/cash(현금)/equity(평가자산)가 "
        "노드 배선 없이 자동으로 포함되어 있어 조건식(expr)에서 바로 참조 가능합니다.\n\n"
        "그래프 편집 규칙(changed=true일 때만 적용):\n"
        "1. scheduler.* 타입 노드는 정확히 1개만 포함하고, 진입 간선이 없는 시작 노드로 둡니다.\n"
        "2. 모든 노드는 scheduler 노드로부터 도달 가능해야 합니다(고아 노드 금지).\n"
        "3. edges는 {\"from\": 노드id, \"to\": 노드id} 형식입니다.\n"
        "4. 각 노드의 params는 param_schema에 정의된 key만 사용합니다.\n"
        "5. 기존 노드의 id는 특별한 이유가 없으면 유지하세요.\n\n"
        "반드시 다음 JSON 형식으로만 응답하세요(다른 텍스트 금지):\n"
        '{"reply": "...", "changed": true 또는 false, "name": "전략 이름", '
        '"nodes": [{"id": "n1", "type": "...", "params": {...}}, ...], '
        '"edges": [{"from": "n1", "to": "n2"}, ...]}'
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(이전 대화 없음)"
    lines = [f"{'사용자' if m.get('role') == 'user' else '어시스턴트'}: {m.get('content', '')}" for m in history[-12:]]
    return "\n".join(lines)


def _build_user_prompt(
    workflow_name: str, graph: dict, selection: dict[str, Any], message: str, history: list[dict]
) -> str:
    return (
        f"현재 워크플로 이름: {workflow_name}\n"
        f"현재 워크플로 그래프 JSON:\n{json.dumps(graph, ensure_ascii=False)}\n\n"
        f"선택 근거 데이터(selection):\n{json.dumps(selection, ensure_ascii=False)}\n\n"
        f"이전 대화:\n{_format_history(history)}\n\n"
        f"사용자 메시지: {message}"
    )


def _unchanged_result(raw: dict) -> dict:
    return {"reply": raw.get("reply", ""), "changed": False, "name": None, "graph": None, "disclaimer": None}


def _changed_result(raw: dict, fallback_name: str) -> dict:
    return {
        "reply": raw.get("reply", ""),
        "changed": True,
        "name": raw.get("name") or fallback_name,
        "graph": {"nodes": raw.get("nodes", []), "edges": raw.get("edges", [])},
        "disclaimer": BACKTEST_EXPLAIN_DISCLAIMER,
    }


def explain_backtest(
    ai_client: AIClient,
    workflow_name: str,
    graph: dict,
    selection: dict[str, Any],
    message: str,
    history: list[dict] | None = None,
) -> dict:
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(workflow_name, graph, selection, message, history or [])

    attempts: list[dict] = []

    raw = ai_client.complete_json(system_prompt, user_prompt)
    if not raw.get("changed"):
        attempts.append({"raw": raw})
        return _unchanged_result(raw)

    graph_dict = {"nodes": raw.get("nodes", []), "edges": raw.get("edges", [])}
    errors = WorkflowGraph.from_dict(graph_dict).validate()
    attempts.append({"raw": raw, "errors": errors})
    if not errors:
        return _changed_result(raw, workflow_name)

    repair_prompt = (
        f"{user_prompt}\n\n"
        "이전 시도가 다음 검증 오류로 실패했습니다. 오류를 모두 해결하여 다시 생성하세요:\n"
        + "\n".join(f"- {e}" for e in errors)
        + f"\n\n이전 시도 JSON:\n{json.dumps(raw, ensure_ascii=False)}"
    )
    raw2 = ai_client.complete_json(system_prompt, repair_prompt)
    if not raw2.get("changed"):
        attempts.append({"raw": raw2})
        return _unchanged_result(raw2)

    graph_dict2 = {"nodes": raw2.get("nodes", []), "edges": raw2.get("edges", [])}
    errors2 = WorkflowGraph.from_dict(graph_dict2).validate()
    attempts.append({"raw": raw2, "errors": errors2})
    if not errors2:
        return _changed_result(raw2, workflow_name)

    raise BacktestExplainError("AI가 제안한 워크플로 변경이 검증을 통과하지 못했습니다.", attempts=attempts)
