"""캔버스 워크플로에 대한 통합 챗봇.

노드 수정 지시("손절 조건 추가해줘")와 진행 상황 설명 요청("지금 이 전략 뭐하는거야?")을
하나의 대화 인터페이스로 처리한다(별도 UI/엔드포인트로 분리하지 않음). AI가 사용자 메시지의
의도를 스스로 판단해 JSON으로 응답하며, `changed` 플래그로 두 경우를 구분한다:
- changed=false: reply만 채워 순수 답변(그래프 검증 생략).
- changed=true: reply와 함께 수정된 전체 그래프를 제시. generate_workflow_draft와 동일하게
  WorkflowGraph.validate()로 검증하고, 실패 시 오류를 포함해 1회 재시도한다.

수정 제안은 이 모듈에서 저장/적용되지 않는다 — 프론트가 미리보기로 보여주고 사용자가
"적용"해야 캔버스에 반영된다(자동 저장/활성화 금지 원칙, workflow_draft.py와 동일).
"""

from __future__ import annotations

import json

from app.ai.base import AIClient
from app.nodes.base import node_registry_schema
from app.workflow.graph import WorkflowGraph

CHAT_DISCLAIMER = (
    "AI가 제안한 워크플로 변경은 투자 판단을 보조하는 참고 정보이며 투자 자문이 아닙니다. "
    "미리보기를 검토한 뒤 '적용'을 눌러야 캔버스에 반영됩니다."
)

MAX_HISTORY_MESSAGES = 12


class WorkflowChatError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


def _build_system_prompt() -> str:
    registry = node_registry_schema()
    return (
        "당신은 노코드 주식 자동매매 전략 빌더의 캔버스를 보조하는 어시스턴트입니다.\n"
        "대화 맥락(history), 현재 워크플로 그래프, (있다면) 최근 테스트 실행 결과를 참고해 답하세요.\n\n"
        "요청 유형을 다음 두 가지로 구분하세요:\n"
        "1. 그래프 수정 지시 -> changed=true로 응답하고, 지시를 반영한 전체 그래프(JSON)를 "
        "nodes/edges에 채우세요. 지시와 무관한 기존 노드/파라미터는 가능한 한 그대로 유지합니다. "
        "reply에는 무엇을 바꿨는지 한두 문장으로 한국어 요약을 담습니다.\n"
        "2. 현재 그래프 구조나 최근 실행 결과에 대한 질문/설명 요청 -> changed=false로 응답하고, "
        "reply에 자연어로 설명합니다. 이 경우 nodes/edges는 빈 배열로 둡니다.\n\n"
        "사용 가능한 노드 타입 (type, category, param_schema):\n"
        f"{json.dumps(registry, ensure_ascii=False, indent=2)}\n\n"
        "모든 종목 데이터에는 held_qty(보유수량)/held_avg_price(평단가)/cash(현금)/equity(평가자산)가 "
        "노드 배선 없이 자동으로 포함되어 있어 조건식(expr)에서 바로 참조 가능합니다.\n\n"
        "그래프 편집 규칙(changed=true일 때만 적용):\n"
        "1. scheduler.* 타입 노드는 정확히 1개만 포함하고, 진입 간선이 없는 시작 노드로 둡니다.\n"
        "2. 모든 노드는 scheduler 노드로부터 도달 가능해야 합니다(고아 노드 금지).\n"
        "3. edges는 {\"from\": 노드id, \"to\": 노드id} 형식입니다.\n"
        "4. 각 노드의 params는 param_schema에 정의된 key만 사용합니다.\n"
        "5. 기존 노드의 id는 특별한 이유가 없으면 유지하세요(사용자가 삭제를 요청한 경우 제외).\n\n"
        "반드시 다음 JSON 형식으로만 응답하세요(다른 텍스트 금지):\n"
        '{"reply": "...", "changed": true 또는 false, "name": "전략 이름", '
        '"nodes": [{"id": "n1", "type": "...", "params": {...}}, ...], '
        '"edges": [{"from": "n1", "to": "n2"}, ...]}'
    )


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(이전 대화 없음)"
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    lines = [f"{'사용자' if m.get('role') == 'user' else '어시스턴트'}: {m.get('content', '')}" for m in trimmed]
    return "\n".join(lines)


def _format_last_run(last_run: dict | None) -> str:
    if not last_run:
        return "(최근 실행 이력 없음)"
    return json.dumps(last_run, ensure_ascii=False)


def _build_user_prompt(
    name: str, graph: dict, message: str, history: list[dict], last_run: dict | None
) -> str:
    return (
        f"현재 워크플로 이름: {name}\n"
        f"현재 워크플로 그래프 JSON:\n{json.dumps(graph, ensure_ascii=False)}\n\n"
        f"최근 테스트 실행 결과:\n{_format_last_run(last_run)}\n\n"
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
        "disclaimer": CHAT_DISCLAIMER,
    }


def chat_about_workflow(
    ai_client: AIClient,
    name: str,
    graph: dict,
    message: str,
    history: list[dict] | None = None,
    last_run: dict | None = None,
) -> dict:
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(name, graph, message, history or [], last_run)

    attempts: list[dict] = []

    raw = ai_client.complete_json(system_prompt, user_prompt, purpose="workflow_chat")
    if not raw.get("changed"):
        attempts.append({"raw": raw})
        return _unchanged_result(raw)

    graph_dict = {"nodes": raw.get("nodes", []), "edges": raw.get("edges", [])}
    errors = WorkflowGraph.from_dict(graph_dict).validate()
    attempts.append({"raw": raw, "errors": errors})
    if not errors:
        return _changed_result(raw, name)

    repair_prompt = (
        f"{user_prompt}\n\n"
        "이전 시도가 다음 검증 오류로 실패했습니다. 오류를 모두 해결하여 다시 생성하세요:\n"
        + "\n".join(f"- {e}" for e in errors)
        + f"\n\n이전 시도 JSON:\n{json.dumps(raw, ensure_ascii=False)}"
    )
    raw2 = ai_client.complete_json(system_prompt, repair_prompt, purpose="workflow_chat")
    if not raw2.get("changed"):
        attempts.append({"raw": raw2})
        return _unchanged_result(raw2)

    graph_dict2 = {"nodes": raw2.get("nodes", []), "edges": raw2.get("edges", [])}
    errors2 = WorkflowGraph.from_dict(graph_dict2).validate()
    attempts.append({"raw": raw2, "errors": errors2})
    if not errors2:
        return _changed_result(raw2, name)

    raise WorkflowChatError("AI가 제안한 워크플로 변경이 검증을 통과하지 못했습니다.", attempts=attempts)
