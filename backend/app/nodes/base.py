"""Node ABC와 노드 레지스트리.

모든 전략 노드는 Node를 상속하고 @register_node로 등록한다.
등록된 노드는 NODE_REGISTRY를 통해 조회되며, GET /nodes API가 이를 그대로
프론트엔드 노드 팔레트/속성 패널 스키마로 노출한다.

description은 노드 팔레트 툴팁뿐 아니라 app/ai/workflow_draft.py, app/ai/workflow_chat.py가
node_registry_schema()를 그대로 프롬프트에 주입할 때 AI가 노드의 역할과 입력/출력
심볼 키를 파악하는 유일한 근거이므로, 각 노드가 symbols에서 무엇을 읽고 무엇을 쓰는지
구체적으로 적는다(예: "symbols[code]에 ma_{window}를 채운다").
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal, TypedDict

RunMode = Literal["live", "test", "backtest"]


class NodeParam(TypedDict, total=False):
    key: str
    type: str  # "string" | "number" | "boolean" | "select" | "expression"
    label: str
    default: Any
    required: bool
    options: list[str]  # type == "select"인 경우 선택지(값)
    option_labels: list[str]  # options와 같은 길이의 사람이 읽는 라벨(프리셋 표시용)
    group: str  # "calc"(계산용 파라미터) | "condition"(매매 조건) — 프론트 입력 그룹 구분
    hint: str  # 입력 도움말(예: "5, 20, 60, 120")
    show_if: dict[str, str]  # {"param": <다른 키>, "equals": <값>}일 때만 노출(조건부 필드)


@dataclass
class NodeContext:
    """워크플로 실행 중 노드 사이를 오가는 데이터.

    symbols: 종목코드 -> 해당 종목에 누적된 데이터(가격, 지표, 점수 등).
    meta: 트리거 정보, 스킵 여부, 브랜치 태그 등 종목에 종속되지 않는 정보.
    """

    run_id: str
    mode: RunMode
    timestamp: datetime
    symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "NodeContext":
        return NodeContext(
            run_id=self.run_id,
            mode=self.mode,
            timestamp=self.timestamp,
            symbols=copy.deepcopy(self.symbols),
            meta=copy.deepcopy(self.meta),
        )

    def snapshot(self) -> dict[str, Any]:
        """이벤트 로깅/디버그 패널 전송용 JSON 직렬화 가능 스냅샷."""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "timestamp": self.timestamp.isoformat(),
            "symbols": self.symbols,
            "meta": self.meta,
        }

    def merged_with(self, other: "NodeContext") -> "NodeContext":
        """다중 입력 병합: 동일 종목은 other 값으로 덮어쓰되 두 컨텍스트의 종목 합집합을 취한다."""
        merged = self.clone()
        for symbol, data in other.symbols.items():
            merged.symbols.setdefault(symbol, {}).update(data)
        merged.meta.update(other.meta)
        return merged


class Node(ABC):
    """모든 전략 노드의 베이스 클래스."""

    type: ClassVar[str]
    category: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""
    subcategory: ClassVar[str] = ""  # 분류(예: 추세/모멘텀/변동성/거래량) — 팔레트 2차 그룹핑용
    example: ClassVar[str] = ""  # 매매 신호 발생 예시(팔레트 툴팁용)
    param_schema: ClassVar[list[NodeParam]] = []

    def __init__(self, node_id: str, params: dict[str, Any] | None = None):
        self.node_id = node_id
        self.params = params or {}

    def validate_params(self) -> list[str]:
        errors: list[str] = []
        for spec in self.param_schema:
            if spec.get("required") and spec["key"] not in self.params:
                errors.append(f"'{spec['key']}' 파라미터가 필요합니다 ({self.display_name}).")
        return errors

    def get_param(self, key: str, default: Any = None) -> Any:
        if key in self.params:
            return self.params[key]
        for spec in self.param_schema:
            if spec["key"] == key:
                return spec.get("default", default)
        return default

    @abstractmethod
    def execute(self, context: NodeContext, **providers: Any) -> NodeContext:
        """context를 입력받아 새 NodeContext를 반환한다.

        providers: market_data / broker 등 워크플로 엔진이 주입하는 외부 의존성(optional).
        """
        raise NotImplementedError


NODE_REGISTRY: dict[str, type[Node]] = {}


def register_node(cls: type[Node]) -> type[Node]:
    if not getattr(cls, "type", None):
        raise ValueError(f"{cls.__name__}에 'type' 클래스 속성이 정의되어야 합니다.")
    NODE_REGISTRY[cls.type] = cls
    return cls


def create_node(node_type: str, node_id: str, params: dict[str, Any] | None = None) -> Node:
    if node_type not in NODE_REGISTRY:
        raise KeyError(f"등록되지 않은 노드 타입: {node_type}")
    return NODE_REGISTRY[node_type](node_id, params)


def node_registry_schema() -> list[dict[str, Any]]:
    """GET /nodes 응답용 스키마 리스트."""
    return [
        {
            "type": cls.type,
            "category": cls.category,
            "subcategory": cls.subcategory,
            "display_name": cls.display_name,
            "description": cls.description,
            "example": cls.example,
            "param_schema": cls.param_schema,
        }
        for cls in NODE_REGISTRY.values()
    ]
