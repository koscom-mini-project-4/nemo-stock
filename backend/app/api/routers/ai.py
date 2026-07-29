from __future__ import annotations

import json
import queue
import threading
from datetime import datetime
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.ai.backtest_explain import BacktestExplainError, explain_backtest
from app.ai.base import AIClient, AIUnavailableError
from app.ai.workflow_chat import WorkflowChatError, chat_about_workflow
from app.ai.workflow_draft import WorkflowDraftError, generate_workflow_draft
from app.api.deps import get_ai_client, get_container
from app.dao.base import NodeEventRecord
from app.dependencies import Container
from app.nodes.ai.news_signal import resolve_news_signal_clusters
from app.workflow.graph import WorkflowGraph
from app.schemas.ai import (
    AIUsageDelta,
    BacktestExplainRequest,
    BacktestExplainResponse,
    GenerateDraftRequest,
    GenerateDraftResponse,
    WorkflowChatRequest,
    WorkflowChatResponse,
)

router = APIRouter(prefix="/ai", tags=["ai"])


def _usage_delta(container: Container, since: datetime) -> AIUsageDelta | None:
    """since 이후 새로 쌓인 AI 사용량(§0-6 AIUsageRepository)을 합산한다(§0-11) — 이 요청
    "1건"이 실제로 얼마나 썼는지를 호출 전/후 델타로 근사한다(정확한 요청 단위 계측 훅을
    추가하는 대신 기존 조회 메서드를 재사용, 관리자 페이지 사용량 통계와 동일 소스)."""
    records = container.ai_usage_repo.list_since(since)
    if not records:
        return None
    return AIUsageDelta(
        prompt_tokens=sum(r.prompt_tokens for r in records),
        completion_tokens=sum(r.completion_tokens for r in records),
        total_tokens=sum(r.total_tokens for r in records),
    )


def _error_frame(exc: Exception) -> dict:
    """블로킹 엔드포인트의 HTTPException 매핑(§0-11 이전부터 있던 것)과 동일한 상태/문구를
    SSE 프레임 안에 담는다 — 스트림 중에는 HTTP 상태 코드로 에러를 표현할 수 없어서다."""
    if isinstance(exc, AIUnavailableError):
        return {"status": 400, "detail": str(exc)}
    if hasattr(exc, "attempts"):  # WorkflowDraftError/WorkflowChatError/BacktestExplainError 공통
        return {"status": 422, "detail": {"message": str(exc), "attempts": exc.attempts}}  # type: ignore[attr-defined]
    return {"status": 500, "detail": str(exc)}


def _stream_sse(worker: Callable[[Callable[[str], None]], dict]) -> Iterator[str]:
    """worker(on_chunk)를 별도 스레드에서 실행하며 원문 텍스트 조각을 실시간 SSE로 흘려보내고
    (§0-18), 완료되면 worker의 반환값을 최종 result 프레임으로, 예외는 error 프레임으로
    변환한다. FastAPI가 동기 제너레이터를 자동으로 스레드풀에서 돌려주므로 async 불필요."""
    q: queue.Queue = queue.Queue()
    outcome: dict[str, Any] = {}

    def on_chunk(text: str) -> None:
        q.put({"type": "chunk", "text": text})

    def run() -> None:
        try:
            outcome["result"] = worker(on_chunk)
        except Exception as exc:  # noqa: BLE001 - 어떤 예외든 error 프레임으로 변환해 스트림을 정상 종료해야 한다
            outcome["error"] = exc
        finally:
            q.put(None)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    while True:
        item = q.get()
        if item is None:
            break
        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    thread.join()

    if "error" in outcome:
        frame = {"type": "error", **_error_frame(outcome["error"])}
    else:
        frame = {"type": "result", **outcome["result"]}
    yield f"data: {json.dumps(frame, ensure_ascii=False, default=str)}\n\n"


@router.post("/generate-draft", response_model=GenerateDraftResponse)
def generate_draft(
    payload: GenerateDraftRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> GenerateDraftResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    called_at = datetime.now()
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

    return GenerateDraftResponse(**draft, usage=_usage_delta(container, called_at))


@router.post("/generate-draft/stream")
def generate_draft_stream(
    payload: GenerateDraftRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """generate_draft(§0-11 이전)와 동일한 로직이지만 생성 중인 원문을 SSE로 실시간
    전송한다(§0-18). chunk 프레임을 여러 번 보낸 뒤 result/error 프레임 하나로 끝난다."""
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    called_at = datetime.now()
    default_universe = ",".join(payload.universe) if payload.universe else None

    def worker(on_chunk: Callable[[str], None]) -> dict:
        if default_universe:
            draft = generate_workflow_draft(
                ai_client, payload.idea, default_universe=default_universe, on_chunk=on_chunk
            )
        else:
            draft = generate_workflow_draft(ai_client, payload.idea, on_chunk=on_chunk)
        usage = _usage_delta(container, called_at)
        return {**draft, "usage": usage.model_dump() if usage else None}

    return StreamingResponse(_stream_sse(worker), media_type="text/event-stream")


@router.post("/workflow-chat", response_model=WorkflowChatResponse)
def workflow_chat(
    payload: WorkflowChatRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> WorkflowChatResponse:
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    called_at = datetime.now()
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

    return WorkflowChatResponse(**result, usage=_usage_delta(container, called_at))


@router.post("/workflow-chat/stream")
def workflow_chat_stream(
    payload: WorkflowChatRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """workflow_chat과 동일한 로직이지만 생성 중인 원문을 SSE로 실시간 전송한다(§0-18)."""
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    called_at = datetime.now()

    def worker(on_chunk: Callable[[str], None]) -> dict:
        result = chat_about_workflow(
            ai_client,
            payload.name,
            payload.graph,
            payload.message,
            history=[m.model_dump() for m in payload.history],
            last_run=payload.last_run,
            on_chunk=on_chunk,
        )
        usage = _usage_delta(container, called_at)
        return {**result, "usage": usage.model_dump() if usage else None}

    return StreamingResponse(_stream_sse(worker), media_type="text/event-stream")


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
        # 노드 타입과 무관하게(logic.if_else/risk.stop_loss/indicator.rsi_signal/
        # ai.news_signal 등 모든 필터형 노드가 공통으로 씀) 종목별 통과/탈락 판단 사유를
        # 담는다 — ai.news_signal은 여기에 실제 참고한 뉴스 제목/기여점수까지 텍스트로
        # 담겨 있어(app/nodes/ai/news_signal.py), 이걸 안 실으면 AI가 "왜 샀는지" 설명할 때
        # 뉴스 근거를 전혀 못 본다(이전까지의 누락).
        decisions = event.output_json.get("meta", {}).get("decisions", {}).get(event.node_id)
        if decisions:
            entry["decisions"] = decisions
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

    # used_news는 data.news(구 파이프라인)만 알고 ai.news_signal이 쓰는 newsstock.db 클러스터는
    # 전혀 모른다(§0-6에서 마커 엔드포인트는 고쳤지만 여기는 그때 놓쳤던 사각지대) — 워크플로에
    # ai.news_signal 노드가 있으면 같은 조회 로직(resolve_news_signal_clusters)을 공유해 실제
    # 참고한 뉴스 클러스터 원문을 selection에 함께 싣는다.
    news_signal_clusters: list[dict[str, Any]] = []
    graph_obj = WorkflowGraph.from_dict(workflow.graph)
    news_signal_node = next((n for n in graph_obj.nodes.values() if n.type == "ai.news_signal"), None)
    if news_signal_node is not None:
        news_signal_clusters = resolve_news_signal_clusters(
            news_signal_node,
            sel.symbol,
            datetime.fromisoformat(start_date).date(),
            datetime.fromisoformat(end_date).date(),
            container.news_trader_factory,
        )

    selection = {
        "kind": sel.kind,
        "symbol": sel.symbol,
        "start_date": start_date,
        "end_date": end_date,
        "trades": trades_in_range,
        "daily_summaries": daily_summaries,
        "price_series": price_series,
        "used_news": used_news,
        "news_signal_clusters": news_signal_clusters,
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

    called_at = datetime.now()
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

    return BacktestExplainResponse(**result, usage=_usage_delta(container, called_at))


@router.post("/backtest-explain/stream")
def backtest_explain_stream(
    payload: BacktestExplainRequest,
    ai_client: AIClient = Depends(get_ai_client),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    """backtest_explain과 동일한 로직이지만 생성 중인 원문을 SSE로 실시간 전송한다(§0-18).
    selection 조립(404 가능성 있음)은 스트림 시작 전에 끝내 일반 HTTPException으로 처리하고,
    AI 호출 이후의 오류만 error 프레임으로 표현한다."""
    if not ai_client.available:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    called_at = datetime.now()
    workflow_name, graph, selection = _build_backtest_selection(payload, container)

    def worker(on_chunk: Callable[[str], None]) -> dict:
        result = explain_backtest(
            ai_client,
            workflow_name,
            graph,
            selection,
            payload.message,
            history=[m.model_dump() for m in payload.history],
            on_chunk=on_chunk,
        )
        usage = _usage_delta(container, called_at)
        return {**result, "usage": usage.model_dump() if usage else None}

    return StreamingResponse(_stream_sse(worker), media_type="text/event-stream")
