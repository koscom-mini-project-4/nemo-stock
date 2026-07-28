"""워크플로 그래프: JSON 정의 파싱 + 검증 + 위상 정렬(Kahn 알고리즘)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.nodes.base import NODE_REGISTRY


@dataclass
class NodeDef:
    id: str
    type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeDef:
    from_: str
    to: str
    branch: str | None = None  # 예: "true"/"false" (logic 노드 분기 표시용, MVP에서는 정보성)


class WorkflowValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class WorkflowGraph:
    nodes: dict[str, NodeDef]
    edges: list[EdgeDef]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowGraph":
        nodes = {
            n["id"]: NodeDef(id=n["id"], type=n["type"], params=n.get("params", {}))
            for n in data.get("nodes", [])
        }
        edges = [
            EdgeDef(from_=e["from"], to=e["to"], branch=e.get("branch"))
            for e in data.get("edges", [])
        ]
        return cls(nodes=nodes, edges=edges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [{"id": n.id, "type": n.type, "params": n.params} for n in self.nodes.values()],
            "edges": [{"from": e.from_, "to": e.to, **({"branch": e.branch} if e.branch else {})} for e in self.edges],
        }

    def predecessors(self, node_id: str) -> list[str]:
        return [e.from_ for e in self.edges if e.to == node_id]

    def successors(self, node_id: str) -> list[str]:
        return [e.to for e in self.edges if e.from_ == node_id]

    def validate(self) -> list[str]:
        errors: list[str] = []

        if not self.nodes:
            errors.append("워크플로에 노드가 없습니다.")
            return errors

        # 1. 노드 타입 존재 여부 + 파라미터 검증
        for node in self.nodes.values():
            if node.type not in NODE_REGISTRY:
                errors.append(f"등록되지 않은 노드 타입: {node.type} (node_id={node.id})")
                continue
            node_cls = NODE_REGISTRY[node.type]
            instance = node_cls(node.id, node.params)
            errors.extend(instance.validate_params())

        # 2. 간선의 노드 참조 유효성
        for edge in self.edges:
            if edge.from_ not in self.nodes:
                errors.append(f"간선의 출발 노드가 존재하지 않습니다: {edge.from_}")
            if edge.to not in self.nodes:
                errors.append(f"간선의 도착 노드가 존재하지 않습니다: {edge.to}")
        if errors:
            return errors

        # 3. 스케줄러 노드는 정확히 1개, 진입 간선 없음
        scheduler_nodes = [n for n in self.nodes.values() if n.type.startswith("scheduler.")]
        if len(scheduler_nodes) != 1:
            errors.append(f"스케줄러 노드는 정확히 1개여야 합니다 (현재 {len(scheduler_nodes)}개).")
        else:
            root = scheduler_nodes[0]
            if self.predecessors(root.id):
                errors.append("스케줄러 노드는 진입 간선을 가질 수 없습니다.")

        # 4. 사이클 검증 겸 위상 정렬 시도
        try:
            order = self.topological_order()
        except WorkflowValidationError as exc:
            errors.extend(exc.errors)
            return errors

        # 5. 고아 노드(스케줄러로부터 도달 불가) 경고
        if scheduler_nodes:
            reachable = self._reachable_from(scheduler_nodes[0].id)
            for node_id in self.nodes:
                if node_id not in reachable:
                    errors.append(f"스케줄러로부터 도달할 수 없는 노드입니다: {node_id}")

        return errors

    def _reachable_from(self, start: str) -> set[str]:
        seen = {start}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for nxt in self.successors(cur):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def ancestors_of(self, node_id: str) -> set[str]:
        """node_id 자신을 포함해, 그 노드가 실행되려면 먼저 실행돼야 하는 조상 노드 집합
        (역방향 BFS). 노드 단독 테스트 실행(§0-9)에서 "이 노드까지만" 범위를 계산하는 데 쓴다."""
        seen = {node_id}
        queue = deque([node_id])
        while queue:
            cur = queue.popleft()
            for prev in self.predecessors(cur):
                if prev not in seen:
                    seen.add(prev)
                    queue.append(prev)
        return seen

    def topological_order(self) -> list[str]:
        """Kahn 알고리즘. 사이클이 있으면 WorkflowValidationError를 발생시킨다."""
        in_degree = {node_id: 0 for node_id in self.nodes}
        for edge in self.edges:
            if edge.to in in_degree:
                in_degree[edge.to] += 1

        queue: deque[str] = deque(sorted(n for n, d in in_degree.items() if d == 0))
        order: list[str] = []

        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for succ in sorted(self.successors(node_id)):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(order) != len(self.nodes):
            remaining = set(self.nodes) - set(order)
            raise WorkflowValidationError([f"워크플로 그래프에 사이클이 존재합니다: {sorted(remaining)}"])

        return order

    def get_node(self, node_id: str) -> NodeDef:
        return self.nodes[node_id]
