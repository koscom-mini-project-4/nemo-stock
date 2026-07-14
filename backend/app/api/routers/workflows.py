from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_container
from app.auth.security import get_current_username
from app.dao.base import RunRecord, WorkflowRecord
from app.dependencies import Container
from app.schemas.workflow import (
    NodeEventOut,
    RunOverride,
    RunResultOut,
    ValidationResult,
    WorkflowCreate,
    WorkflowOut,
    WorkflowUpdate,
)
from app.workflow.graph import WorkflowGraph, WorkflowValidationError

router = APIRouter(prefix="/workflows", tags=["workflows"], dependencies=[Depends(get_current_username)])

_DEFAULT_USER_ID = "admin"  # 단일 계정 PoC


def _to_out(w: WorkflowRecord) -> WorkflowOut:
    return WorkflowOut(
        id=w.id,
        user_id=w.user_id,
        name=w.name,
        graph=w.graph,
        status=w.status,
        schedule_interval_sec=w.schedule_interval_sec,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


@router.get("", response_model=list[WorkflowOut])
def list_workflows(container: Container = Depends(get_container)) -> list[WorkflowOut]:
    return [_to_out(w) for w in container.workflow_repo.list_by_user(_DEFAULT_USER_ID)]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, container: Container = Depends(get_container)) -> WorkflowOut:
    graph_dict = payload.graph.model_dump(by_alias=True)
    errors = WorkflowGraph.from_dict(graph_dict).validate()
    now = datetime.now()
    record = WorkflowRecord(
        id=str(uuid.uuid4()),
        user_id=_DEFAULT_USER_ID,
        name=payload.name,
        graph=graph_dict,
        status="draft",
        schedule_interval_sec=payload.schedule_interval_sec,
        created_at=now,
        updated_at=now,
    )
    container.workflow_repo.save(record)
    out = _to_out(record)
    if errors:
        # 저장은 허용하되(초안 편집 중일 수 있음) 검증 오류는 응답 헤더성 정보로 남기지 않고
        # 별도 /validate 호출로 확인하도록 유도한다. 여기서는 활성화만 막는다.
        pass
    return out


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, container: Container = Depends(get_container)) -> WorkflowOut:
    w = container.workflow_repo.get(workflow_id)
    if w is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")
    return _to_out(w)


@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: str, payload: WorkflowUpdate, container: Container = Depends(get_container)
) -> WorkflowOut:
    w = container.workflow_repo.get(workflow_id)
    if w is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")
    if payload.name is not None:
        w.name = payload.name
    if payload.graph is not None:
        w.graph = payload.graph.model_dump(by_alias=True)
    if payload.schedule_interval_sec is not None:
        w.schedule_interval_sec = payload.schedule_interval_sec
    if payload.status is not None:
        if payload.status == "active":
            errors = WorkflowGraph.from_dict(w.graph).validate()
            if errors:
                raise HTTPException(status_code=422, detail={"message": "활성화 전 검증 실패", "errors": errors})
        w.status = payload.status
    w.updated_at = datetime.now()
    container.workflow_repo.save(w)
    return _to_out(w)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str, container: Container = Depends(get_container)) -> None:
    container.workflow_repo.delete(workflow_id)


@router.post("/{workflow_id}/validate", response_model=ValidationResult)
def validate_workflow(workflow_id: str, container: Container = Depends(get_container)) -> ValidationResult:
    w = container.workflow_repo.get(workflow_id)
    if w is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")
    graph = WorkflowGraph.from_dict(w.graph)
    errors = graph.validate()
    order: list[str] = []
    if not errors:
        order = graph.topological_order()
    return ValidationResult(valid=not errors, errors=errors, execution_order=order)


@router.post("/{workflow_id}/run", response_model=RunResultOut)
def run_workflow(
    workflow_id: str, payload: RunOverride, container: Container = Depends(get_container)
) -> RunResultOut:
    """테스트 실행: overrides로 특정 노드의 종목별 출력값을 임의 지정할 수 있다."""
    w = container.workflow_repo.get(workflow_id)
    if w is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")

    graph = WorkflowGraph.from_dict(w.graph)
    if payload.universe:
        for node in graph.nodes.values():
            if node.type.startswith("scheduler."):
                node.params["universe"] = ",".join(payload.universe)

    run_id = str(uuid.uuid4())
    started_at = datetime.now()
    run_record = RunRecord(id=run_id, workflow_id=workflow_id, mode="test", status="running", started_at=started_at)
    container.run_repo.save(run_record)

    try:
        result = container.engine.execute(
            workflow_id=workflow_id,
            graph=graph,
            mode="test",
            market_data=container.market_data,
            broker=container.broker,
            overrides=payload.overrides,
            run_id=run_id,
        )
    except WorkflowValidationError as exc:
        run_record.status = "error"
        run_record.error = "; ".join(exc.errors)
        run_record.finished_at = datetime.now()
        container.run_repo.save(run_record)
        raise HTTPException(status_code=422, detail={"message": "워크플로 검증 실패", "errors": exc.errors}) from exc

    run_record.status = result.status
    run_record.error = result.error
    run_record.finished_at = result.finished_at
    container.run_repo.save(run_record)

    events = container.event_bus.get_history(run_id)
    final_ctx = result.final_context
    return RunResultOut(
        run_id=result.run_id,
        workflow_id=workflow_id,
        mode=result.mode,
        status=result.status,
        started_at=result.started_at,
        finished_at=result.finished_at,
        error=result.error,
        events=[
            NodeEventOut(
                node_id=e.node_id,
                node_type=e.node_type,
                status=e.status,
                timestamp=e.timestamp,
                input_snapshot=e.input_snapshot,
                output_snapshot=e.output_snapshot,
                error=e.error,
                duration_ms=e.duration_ms,
            )
            for e in events
        ],
        final_symbols=final_ctx.symbols if final_ctx else {},
    )
