from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeIn(BaseModel):
    id: str
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class EdgeIn(BaseModel):
    from_: str = Field(alias="from")
    to: str
    branch: str | None = None

    model_config = {"populate_by_name": True}


class WorkflowGraphIn(BaseModel):
    nodes: list[NodeIn]
    edges: list[EdgeIn]


class WorkflowCreate(BaseModel):
    name: str
    graph: WorkflowGraphIn
    schedule_interval_sec: int = 60


class WorkflowUpdate(BaseModel):
    name: str | None = None
    graph: WorkflowGraphIn | None = None
    schedule_interval_sec: int | None = None
    status: Literal["draft", "active", "inactive"] | None = None


class WorkflowOut(BaseModel):
    id: str
    user_id: str
    name: str
    graph: dict[str, Any]
    status: str
    schedule_interval_sec: int
    created_at: datetime
    updated_at: datetime


class WorkflowTemplateOut(BaseModel):
    id: str
    name: str
    description: str
    graph: dict[str, Any]


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)


class RunOverride(BaseModel):
    # node_id -> symbol -> {field: value}
    overrides: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    universe: list[str] | None = None
    # 지정하면 그 노드와 조상 노드만 실행한다(노드 단독 테스트, §0-9).
    target_node_id: str | None = None


class NodeEventOut(BaseModel):
    node_id: str
    node_type: str
    status: str
    timestamp: datetime
    input_snapshot: dict[str, Any] | None = None
    output_snapshot: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None


class RunResultOut(BaseModel):
    run_id: str
    workflow_id: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime
    error: str | None = None
    events: list[NodeEventOut] = Field(default_factory=list)
    final_symbols: dict[str, Any] = Field(default_factory=dict)
