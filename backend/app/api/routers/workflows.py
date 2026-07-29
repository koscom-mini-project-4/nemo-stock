from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_container
from app.dao.base import RunRecord, WorkflowRecord
from app.dependencies import Container
from app.schemas.workflow import (
    NodeEventOut,
    RunOverride,
    RunResultOut,
    ValidationResult,
    WorkflowCreate,
    WorkflowOut,
    WorkflowPnlOut,
    WorkflowTemplateOut,
    WorkflowUpdate,
)
from app.workflow.graph import WorkflowGraph, WorkflowValidationError
from app.workflow.pnl import compute_workflow_pnl, load_workflow_fills
from app.workflow.run_persistence import events_to_records
from app.workflow.templates import get_templates

router = APIRouter(prefix="/workflows", tags=["workflows"])

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


@router.get("/templates", response_model=list[WorkflowTemplateOut])
def list_workflow_templates() -> list[WorkflowTemplateOut]:
    """/{workflow_id}보다 먼저 등록해야 "templates"가 workflow_id로 잘못 매칭되지 않는다."""
    return [
        WorkflowTemplateOut(id=t.id, name=t.name, description=t.description, graph=t.graph)
        for t in get_templates()
    ]


@router.get("/pnl-summary", response_model=list[WorkflowPnlOut])
def list_workflow_pnl(container: Container = Depends(get_container)) -> list[WorkflowPnlOut]:
    """/{workflow_id}보다 먼저 등록해야 "pnl-summary"가 workflow_id로 잘못 매칭되지 않는다.

    각 워크플로의 live/test run 체결 이력으로부터 근사 손익을 계산한다(app/workflow/pnl.py 참고).
    """
    workflows = container.workflow_repo.list_by_user(_DEFAULT_USER_ID)
    all_runs = [run for w in workflows for run in container.run_repo.list_by_workflow(w.id)]

    price_cache: dict[str, float | None] = {}

    def current_price(symbol: str) -> float | None:
        if symbol not in price_cache:
            try:
                price_cache[symbol] = container.market_data.get_price(symbol).price
            except Exception:
                price_cache[symbol] = None
        return price_cache[symbol]

    results = []
    for w in workflows:
        fills = load_workflow_fills(w.id, all_runs, container.node_event_repo.list_by_run)
        pnl = compute_workflow_pnl(w.id, fills, current_price)
        results.append(
            WorkflowPnlOut(
                workflow_id=pnl.workflow_id,
                realized_pnl=pnl.realized_pnl,
                unrealized_pnl=pnl.unrealized_pnl,
                total_pnl=pnl.total_pnl,
                total_invested=pnl.total_invested,
                return_pct=pnl.return_pct,
                trade_count=pnl.trade_count,
            )
        )
    return results


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
            extra_providers=container.node_providers(),
            target_node_id=payload.target_node_id,
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
    # 라이브(WorkerPool)/백테스트(BacktestRunner)와 동일하게 노드 이벤트를 영속화한다 — 테스트
    # 실행도 같은 공용 포트폴리오(container.broker)에 실제 체결을 남기므로, 전략별 손익 집계
    # (app/workflow/pnl.py)와 GET /runs/{run_id} 재생이 테스트 실행에도 동작해야 한다.
    container.node_event_repo.save_many(events_to_records(container.event_bus, run_id))

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


@router.get("/{workflow_id}/runs/{run_id}", response_model=RunResultOut)
def get_run(workflow_id: str, run_id: str, container: Container = Depends(get_container)) -> RunResultOut:
    """저장된 run(라이브/테스트/백테스트 공용) 1건의 실행 결과를 조회한다.

    백테스트 결과 화면에서 특정 날짜를 골라 그날의 노드 그래프 실행을 "테스트 실행"과 동일한
    디버그 패널로 재생할 때 사용한다(DESIGN.md §8, 백테스트는 거래일마다 별도 run_id로 저장됨).
    """
    run = container.run_repo.get(run_id)
    if run is None or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="run을 찾을 수 없습니다.")

    events = container.node_event_repo.list_by_run(run_id)
    final_symbols: dict[str, Any] = {}
    for e in events:
        if e.output_json is not None:
            final_symbols = e.output_json.get("symbols", {})

    return RunResultOut(
        run_id=run.id,
        workflow_id=run.workflow_id,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at or run.started_at,
        error=run.error,
        events=[
            NodeEventOut(
                node_id=e.node_id,
                node_type=e.node_type,
                status=e.status,
                timestamp=e.timestamp,
                input_snapshot=e.input_json,
                output_snapshot=e.output_json,
                error=e.error,
                duration_ms=e.duration_ms,
            )
            for e in events
        ],
        final_symbols=final_symbols,
    )
