from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.ai.backtest_explain import BacktestExplainError, explain_backtest
from app.ai.base import AIClient, AIUnavailableError
from app.ai.workflow_chat import WorkflowChatError, chat_about_workflow
from app.ai.workflow_draft import WorkflowDraftError, generate_workflow_draft
from app.api.deps import get_ai_client, get_container
from app.auth.security import get_current_username
from app.dao.base import NodeEventRecord
from app.dependencies import Container
from app.schemas.ai import (
    BacktestExplainRequest,
    BacktestExplainResponse,
    GenerateDraftRequest,
    GenerateDraftResponse,
    WorkflowChatRequest,
    WorkflowChatResponse,
)

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(get_current_username)])


@router.post("/generate-draft", response_model=GenerateDraftResponse)
def generate_draft(
    payload: GenerateDraftRequest, ai_client: AIClient = Depends(get_ai_client)
) -> GenerateDraftResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    default_universe = ",".join(payload.universe) if payload.universe else None
    try:
        if default_universe:
            draft = generate_workflow_draft(ai_client, payload.idea, default_universe=default_universe)
        else:
            draft = generate_workflow_draft(ai_client, payload.idea)
    except AIUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowDraftError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "attempts": exc.attempts},
        ) from exc

    return GenerateDraftResponse(**draft)


@router.post("/workflow-chat", response_model=WorkflowChatResponse)
def workflow_chat(
    payload: WorkflowChatRequest, ai_client: AIClient = Depends(get_ai_client)
) -> WorkflowChatResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    try:
        result = chat_about_workflow(
            ai_client,
            payload.name,
            payload.graph,
            payload.message,
            history=[m.model_dump() for m in payload.history],
            last_run=payload.last_run,
        )
    except AIUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WorkflowChatError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "attempts": exc.attempts},
        ) from exc

    return WorkflowChatResponse(**result)


def _summarize_day_events(events: list[NodeEventRecord]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for event in events:
        entry: dict[str, Any] = {"node_id": event.node_id, "node_type": event.node_type, "status": event.status}
        if event.status != "success" or not event.output_json:
            if event.error:
                entry["error"] = event.error
            nodes.append(entry)
            continue
        symbols = event.output_json.get("symbols", {})
        entry["symbols"] = list(symbols.keys())
        if event.node_type == "logic.if_else":
            filtered = event.output_json.get("meta", {}).get("filtered_out", {}).get(event.node_id)
            if filtered:
                entry["filtered_out"] = filtered
        if event.node_type == "execution.market_order":
            orders = event.output_json.get("meta", {}).get("orders", [])
            if orders:
                entry["orders"] = orders
        nodes.append(entry)
    return {"nodes": nodes}


def _build_backtest_selection(payload: BacktestExplainRequest, container: Container) -> tuple[str, dict, dict]:
    """반환: (workflow_name, graph, selection dict)."""
    record = container.backtest_result_repo.get(payload.backtest_id)
    if record is None:
        raise HTTPException(status_code=404, detail="백테스트 결과를 찾을 수 없습니다.")
    workflow = container.workflow_repo.get(record.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")

    sel = payload.selection
    if sel.kind == "point":
        start_date = end_date = sel.date or record.start_date.isoformat()
    else:
        start_date = sel.start_date or record.start_date.isoformat()
        end_date = sel.end_date or record.end_date.isoformat()

    days_in_range = [d for d in record.daily_runs if start_date <= d["date"] <= end_date]
    daily_summaries = [
        {"date": d["date"], **_summarize_day_events(container.node_event_repo.list_by_run(d["run_id"]))}
        for d in days_in_range
    ]
    trades_in_range = [
        t for t in record.trades if t["symbol"] == sel.symbol and start_date <= t["date"] <= end_date
    ]

    price_series: list[dict[str, Any]] = []
    if sel.symbol in record.universe:
        bars = container.price_bar_repo.list_range(
            sel.symbol, datetime.fromisoformat(start_date).date(), datetime.fromisoformat(end_date).date()
        )
        price_series = [{"date": b.trade_date.isoformat(), "close": b.close} for b in bars]

    used_news: list[dict[str, Any]] = []
    for d in days_in_range:
        events = container.node_event_repo.list_by_run(d["run_id"])
        for event in events:
            if event.node_type != "data.news" or event.status != "success" or not event.output_json:
                continue
            symbol_data = event.output_json.get("symbols", {}).get(sel.symbol)
            if not symbol_data or not symbol_data.get("news_id"):
                continue
            news = container.news_repo.get(symbol_data["news_id"])
            if news is not None:
                used_news.append({"date": d["date"], "title": news.title, "published_at": news.published_at.isoformat()})

    selection = {
        "kind": sel.kind,
        "symbol": sel.symbol,
        "start_date": start_date,
        "end_date": end_date,
        "trades": trades_in_range,
        "daily_summaries": daily_summaries,
        "price_series": price_series,
        "used_news": used_news,
    }
    return workflow.name, workflow.graph, selection


@router.post("/backtest-explain", response_model=BacktestExplainResponse)
def backtest_explain(
    payload: BacktestExplainRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> BacktestExplainResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    workflow_name, graph, selection = _build_backtest_selection(payload, container)
    try:
        result = explain_backtest(
            ai_client,
            workflow_name,
            graph,
            selection,
            payload.message,
            history=[m.model_dump() for m in payload.history],
        )
    except AIUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BacktestExplainError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "attempts": exc.attempts},
        ) from exc

    return BacktestExplainResponse(**result)
