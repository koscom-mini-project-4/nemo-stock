from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container
from app.auth.security import get_current_username
from app.backtest.runner import BacktestRunner
from app.dao.base import BacktestResultRecord
from app.dependencies import Container
from app.schemas.backtest import BacktestRequest, BacktestResultOut, EquityPoint
from app.workflow.graph import WorkflowGraph

router = APIRouter(prefix="/backtest", tags=["backtest"], dependencies=[Depends(get_current_username)])


def _to_out(r: BacktestResultRecord) -> BacktestResultOut:
    return BacktestResultOut(
        id=r.id,
        workflow_id=r.workflow_id,
        start_date=r.start_date,
        end_date=r.end_date,
        initial_capital=r.initial_capital,
        final_equity=r.final_equity,
        total_return_pct=r.total_return_pct,
        cagr_pct=r.cagr_pct,
        mdd_pct=r.mdd_pct,
        volatility_pct=r.volatility_pct,
        win_rate_pct=r.win_rate_pct,
        profit_loss_ratio=r.profit_loss_ratio,
        trade_count=r.trade_count,
        equity_curve=[EquityPoint(date=e["date"], equity=e["equity"]) for e in r.equity_curve],
        created_at=r.created_at,
    )


@router.post("", response_model=BacktestResultOut, status_code=201)
def run_backtest(payload: BacktestRequest, container: Container = Depends(get_container)) -> BacktestResultOut:
    workflow = container.workflow_repo.get(payload.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")

    graph = WorkflowGraph.from_dict(workflow.graph)
    errors = graph.validate()
    if errors:
        raise HTTPException(status_code=422, detail={"message": "워크플로 검증 실패", "errors": errors})

    runner = BacktestRunner(container.engine, container.price_bar_repo)
    try:
        result = runner.run(
            workflow_id=payload.workflow_id,
            graph=graph,
            universe=payload.universe,
            start=payload.start_date,
            end=payload.end_date,
            initial_capital=payload.initial_capital,
            extra_providers=container.node_providers(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    record = BacktestResultRecord(
        id=str(uuid.uuid4()),
        workflow_id=payload.workflow_id,
        start_date=result.start_date,
        end_date=result.end_date,
        initial_capital=result.initial_capital,
        final_equity=result.final_equity,
        total_return_pct=result.metrics.total_return_pct,
        cagr_pct=result.metrics.cagr_pct,
        mdd_pct=result.metrics.mdd_pct,
        volatility_pct=result.metrics.volatility_pct,
        win_rate_pct=result.metrics.win_rate_pct,
        profit_loss_ratio=result.metrics.profit_loss_ratio,
        trade_count=result.metrics.trade_count,
        equity_curve=[{"date": d.isoformat(), "equity": e} for d, e in result.equity_curve],
    )
    container.backtest_result_repo.save(record)
    return _to_out(record)


@router.get("/{result_id}", response_model=BacktestResultOut)
def get_backtest(result_id: str, container: Container = Depends(get_container)) -> BacktestResultOut:
    record = container.backtest_result_repo.get(result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="백테스트 결과를 찾을 수 없습니다.")
    return _to_out(record)
