"""자연어 투자 아이디어 -> 워크플로 초안 생성 (기획서 Ⅲ.3.가).

노드 레지스트리(NODE_REGISTRY)를 프롬프트에 주입해 AI가 실제 존재하는 노드 타입만
사용하도록 유도하고, 생성된 그래프는 WorkflowGraph.validate()로 재검증한다.
검증 실패 시 오류 메시지를 포함해 한 번 더 시도하고, 그래도 실패하면 사용자에게
원문과 오류를 함께 반환해 수동 수정을 유도한다(자동 저장/활성화하지 않음).
"""

from __future__ import annotations

import json

from app.ai.base import AIClient
from app.nodes.base import node_registry_schema
from app.workflow.graph import WorkflowGraph

DISCLAIMER = (
    "AI가 생성한 전략 초안은 투자 판단을 보조하는 참고 정보이며 투자 자문이 아닙니다. "
    "반드시 내용을 검토하고 수정한 뒤 저장/활성화하십시오."
)

DEFAULT_UNIVERSE = "005930,000660"


class WorkflowDraftError(RuntimeError):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


def _build_system_prompt() -> str:
    registry = node_registry_schema()
    return (
        "당신은 노코드 주식 자동매매 전략 빌더의 워크플로 설계를 돕는 어시스턴트입니다.\n"
        "사용자의 자연어 투자 아이디어를 아래에 정의된 노드 타입만 사용하여 실행 가능한 "
        "워크플로 그래프(JSON)로 변환하세요.\n\n"
        "사용 가능한 노드 타입 (type, category, param_schema):\n"
        f"{json.dumps(registry, ensure_ascii=False, indent=2)}\n\n"
        "모든 종목 데이터에는 held_qty(보유수량)/held_avg_price(평단가)/cash(현금)/equity(평가자산)가 "
        "노드 배선 없이 자동으로 포함되어 있어 조건식(expr)에서 바로 참조 가능합니다.\n\n"
        "규칙:\n"
        "1. scheduler.* 타입 노드는 정확히 1개만 포함하고, 진입 간선이 없는 시작 노드로 둡니다.\n"
        "2. 모든 노드는 scheduler 노드로부터 도달 가능해야 합니다(고아 노드 금지).\n"
        "3. edges는 {\"from\": 노드id, \"to\": 노드id} 형식입니다.\n"
        "4. 각 노드의 params는 param_schema에 정의된 key만 사용합니다.\n"
        "5. 반드시 다음 JSON 형식으로만 응답하세요(다른 텍스트 금지):\n"
        '{"name": "전략 이름", "nodes": [{"id": "n1", "type": "...", "params": {...}}, ...], '
        '"edges": [{"from": "n1", "to": "n2"}, ...]}'
    )


def _coerce_graph_shape(raw: dict) -> dict:
    return {"nodes": raw.get("nodes", []), "edges": raw.get("edges", [])}


def generate_workflow_draft(
    ai_client: AIClient, idea: str, default_universe: str = DEFAULT_UNIVERSE
) -> dict:
    system_prompt = _build_system_prompt()
    user_prompt = (
        f"투자 아이디어: {idea}\n"
        f"사용자가 종목을 명시하지 않았다면 scheduler 노드의 universe 파라미터 기본값으로 "
        f"'{default_universe}'를 사용하세요."
    )

    attempts: list[dict] = []

    raw = ai_client.complete_json(system_prompt, user_prompt)
    graph_dict = _coerce_graph_shape(raw)
    errors = WorkflowGraph.from_dict(graph_dict).validate()
    attempts.append({"raw": raw, "errors": errors})
    if not errors:
        return {"name": raw.get("name") or idea[:40], "graph": graph_dict, "disclaimer": DISCLAIMER}

    repair_prompt = (
        f"{user_prompt}\n\n"
        "이전 시도가 다음 검증 오류로 실패했습니다. 오류를 모두 해결하여 다시 생성하세요:\n"
        + "\n".join(f"- {e}" for e in errors)
        + f"\n\n이전 시도 JSON:\n{json.dumps(raw, ensure_ascii=False)}"
    )
    raw2 = ai_client.complete_json(system_prompt, repair_prompt)
    graph_dict2 = _coerce_graph_shape(raw2)
    errors2 = WorkflowGraph.from_dict(graph_dict2).validate()
    attempts.append({"raw": raw2, "errors": errors2})
    if not errors2:
        return {"name": raw2.get("name") or idea[:40], "graph": graph_dict2, "disclaimer": DISCLAIMER}

    raise WorkflowDraftError("AI가 생성한 워크플로가 검증을 통과하지 못했습니다.", attempts=attempts)
