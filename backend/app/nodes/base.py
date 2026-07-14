"""Node ABC와 노드 레지스트리.

모든 전략 노드는 Node를 상속하고 @register_node로 등록한다.
등록된 노드는 NODE_REGISTRY를 통해 조회되며, GET /nodes API가 이를 그대로
프론트엔드 노드 팔레트/속성 패널 스키마로 노출한다.
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
    options: list[str]  # type == "select"인 경우 선택지


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
            "display_name": cls.display_name,
            "param_schema": cls.param_schema,
        }
        for cls in NODE_REGISTRY.values()
    ]
