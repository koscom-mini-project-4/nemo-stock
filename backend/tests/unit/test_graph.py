from __future__ import annotations

import pytest

from app.nodes import load_all_nodes
from app.workflow.graph import WorkflowGraph, WorkflowValidationError

load_all_nodes()


def _simple_graph_dict() -> dict:
    return {
        "nodes": [
            {"id": "n1", "type": "scheduler.interval", "params": {"interval_sec": 60, "universe": "005930"}},
            {"id": "n2", "type": "data.price", "params": {}},
            {"id": "n3", "type": "logic.if_else", "params": {"expr": "price > 0"}},
            {"id": "n4", "type": "execution.market_order", "params": {"side": "buy", "qty": 1}},
        ],
        "edges": [
            {"from": "n1", "to": "n2"},
            {"from": "n2", "to": "n3"},
            {"from": "n3", "to": "n4"},
        ],
    }


def test_topological_order_happy_path():
    graph = WorkflowGraph.from_dict(_simple_graph_dict())
    assert graph.validate() == []
    order = graph.topological_order()
    assert order == ["n1", "n2", "n3", "n4"]


def test_cycle_detected():
    data = _simple_graph_dict()
    data["edges"].append({"from": "n4", "to": "n2"})  # 사이클 생성
    graph = WorkflowGraph.from_dict(data)
    errors = graph.validate()
    assert any("사이클" in e for e in errors)
    with pytest.raises(WorkflowValidationError):
        graph.topological_order()


def test_missing_scheduler_node():
    data = _simple_graph_dict()
    data["nodes"] = [n for n in data["nodes"] if n["type"] != "scheduler.interval"]
    data["edges"] = [e for e in data["edges"] if e["from"] != "n1"]
    graph = WorkflowGraph.from_dict(data)
    errors = graph.validate()
    assert any("스케줄러" in e for e in errors)


def test_orphan_node_detected():
    data = _simple_graph_dict()
    data["nodes"].append({"id": "n5", "type": "data.price", "params": {}})
    graph = WorkflowGraph.from_dict(data)
    errors = graph.validate()
    assert any("도달할 수 없는 노드" in e for e in errors)


def test_unknown_node_type_rejected():
    data = _simple_graph_dict()
    data["nodes"][1]["type"] = "data.unknown_type"
    graph = WorkflowGraph.from_dict(data)
    errors = graph.validate()
    assert any("등록되지 않은 노드 타입" in e for e in errors)
