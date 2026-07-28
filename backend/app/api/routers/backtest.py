from __future__ import annotations

import uuid
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_container, get_intraday_price_bar_repo, get_price_ingest_client
from app.auth.security import get_current_username
from app.backtest.runner import BacktestRunner
from app.dao.base import BacktestResultRecord, IntradayPriceBarRepository
from app.data_ingestion.auto_ingest import ensure_price_data
from app.data_ingestion.naver_price_client import NaverStockChartClient
from app.dependencies import Container
from app.market_data.symbol_master import get_symbol_name
from app.nodes.ai.news_signal import AXIS_METHOD
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResultOut,
    DailyRunOut,
    EquityPoint,
    NewsMarkerOut,
    PricePointOut,
    TradeOut,
)
from app.workflow.graph import WorkflowGraph

router = APIRouter(prefix="/backtest", tags=["backtest"], dependencies=[Depends(get_current_username)])

# ai.news_signal(auto_update=true)은 거래일마다 AI 분류를 다시 트리거할 수 있어(뉴스가 실행
# 시점 날짜 기준으로 조회되도록 바뀐 뒤로는 각 거래일이 서로 다른 조회를 만듦), 백테스트 기간이
# 길어질수록 OpenAI 호출이 그만큼 늘어난다. 비용을 예측 가능한 범위로 묶기 위해 이 노드가 포함된
# 백테스트는 기간을 제한한다(2026-07-28 사용자 확인: 4일 → 7일로 상향).
# ai.free_prompt(§0-9)도 심볼×거래일마다 실제 AI 호출이 나가고(도구 호출 모드는 라운드당
# 추가 호출까지) 캐시가 없어 동일한 위험이 있으므로 같은 제한을 적용한다.
NEWS_SIGNAL_BACKTEST_MAX_DAYS = 7
_AI_COST_NODE_TYPES = {"ai.news_signal", "ai.free_prompt"}


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
        daily_runs=[DailyRunOut(date=d["date"], run_id=d["run_id"]) for d in r.daily_runs],
        universe=r.universe,
        trades=[TradeOut(**t) for t in r.trades],
        created_at=r.created_at,
    )


def _get_result_or_404(result_id: str, container: Container) -> BacktestResultRecord:
    record = container.backtest_result_repo.get(result_id)
    if record is None:
        raise HTTPException(status_code=404, detail="백테스트 결과를 찾을 수 없습니다.")
    return record


@router.post("", response_model=BacktestResultOut, status_code=201)
def run_backtest(
    payload: BacktestRequest,
    container: Container = Depends(get_container),
    intraday_repo: IntradayPriceBarRepository = Depends(get_intraday_price_bar_repo),
    price_client: NaverStockChartClient = Depends(get_price_ingest_client),
) -> BacktestResultOut:
    workflow = container.workflow_repo.get(payload.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="워크플로를 찾을 수 없습니다.")

    graph = WorkflowGraph.from_dict(workflow.graph)
    errors = graph.validate()
    if errors:
        raise HTTPException(status_code=422, detail={"message": "워크플로 검증 실패", "errors": errors})

    ai_cost_node_types = sorted({n.type for n in graph.nodes.values() if n.type in _AI_COST_NODE_TYPES})
    period_days = (payload.end_date - payload.start_date).days + 1
    if ai_cost_node_types and period_days > NEWS_SIGNAL_BACKTEST_MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{', '.join(ai_cost_node_types)} 노드가 포함된 워크플로는 AI 호출량 제한을 위해 "
                f"백테스트 기간을 최대 {NEWS_SIGNAL_BACKTEST_MAX_DAYS}일로 제한합니다(요청: {period_days}일)."
            ),
        )

    if container.settings.auto_ingest_prices:
        for symbol in payload.universe:
            ensure_price_data(
                container.price_bar_repo, intraday_repo, price_client, symbol, payload.start_date, payload.end_date
            )

    runner = BacktestRunner(
        container.engine, container.price_bar_repo, container.run_repo, container.node_event_repo, container.event_bus
    )
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
        daily_runs=[{"date": d.isoformat(), "run_id": run_id} for d, run_id in result.daily_runs],
        universe=result.universe,
        trades=[
            {
                "date": d.isoformat(),
                "run_id": run_id,
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": order.qty,
                "price": order.price,
                "status": order.status,
                "reason": order.reason,
                "realized_pnl": order.realized_pnl,
            }
            for d, run_id, order in result.trades
        ],
    )
    container.backtest_result_repo.save(record)
    return _to_out(record)


@router.get("/{result_id}", response_model=BacktestResultOut)
def get_backtest(result_id: str, container: Container = Depends(get_container)) -> BacktestResultOut:
    return _to_out(_get_result_or_404(result_id, container))


@router.get("/{result_id}/prices", response_model=list[PricePointOut])
def get_backtest_prices(
    result_id: str, symbol: str, interval: str = "day", container: Container = Depends(get_container)
) -> list[PricePointOut]:
    """일봉(기본, interval="day") 또는 시간봉(interval="minute60")을 반환한다.

    시간봉은 §0-2 문서화된 실측 한계(네이버 API가 최근 약 8거래일치만 제공)로 오래된 기간은
    항상 빈 배열이다 — 프론트가 빈 배열이면 일봉으로 폴백하는 방식으로 이 한계를 흡수한다.
    백테스트 엔진 자체는 여전히 일봉으로만 동작하며(§8-1), 이건 차트 표시 전용이다.
    """
    record = _get_result_or_404(result_id, container)
    if symbol not in record.universe:
        raise HTTPException(status_code=400, detail="해당 백테스트의 대상 종목이 아닙니다.")

    if interval != "day":
        start = datetime.combine(record.start_date, time.min)
        end = datetime.combine(record.end_date, time.max)
        intraday_bars = container.intraday_price_bar_repo.list_range(symbol, start, end, interval=interval)
        return [
            PricePointOut(
                date=b.bar_datetime.strftime("%Y-%m-%d %H:%M"),
                open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume,
            )
            for b in intraday_bars
        ]

    bars = container.price_bar_repo.list_range(symbol, record.start_date, record.end_date)
    return [
        PricePointOut(
            date=b.trade_date.isoformat(), open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume
        )
        for b in bars
    ]


@router.get("/{result_id}/news/used", response_model=list[NewsMarkerOut])
def get_backtest_news_used(
    result_id: str, symbol: str, container: Container = Depends(get_container)
) -> list[NewsMarkerOut]:
    """그 백테스트 실행 중 워크플로가 실제로(data.news 노드로) 조회한 뉴스만 반환한다."""
    record = _get_result_or_404(result_id, container)
    markers: list[NewsMarkerOut] = []
    for d in record.daily_runs:
        events = container.node_event_repo.list_by_run(d["run_id"])
        for event in events:
            if event.node_type != "data.news" or event.status != "success" or not event.output_json:
                continue
            symbol_data = event.output_json.get("symbols", {}).get(symbol)
            if not symbol_data or not symbol_data.get("news_id"):
                continue
            news = container.news_repo.get(symbol_data["news_id"])
            if news is None:
                continue
            markers.append(
                NewsMarkerOut(
                    date=d["date"],
                    news_id=news.id,
                    title=news.title,
                    published_at=news.published_at.isoformat(),
                    source=news.source,
                    used=True,
                )
            )
    return markers


@router.get("/{result_id}/news/all", response_model=list[NewsMarkerOut])
def get_backtest_news_all(
    result_id: str, symbol: str, container: Container = Depends(get_container)
) -> list[NewsMarkerOut]:
    """워크플로 사용 여부와 무관하게 news 테이블에 적재된 해당 기간 전체 뉴스(체크박스 토글 전용, 가벼운 부가 조회)."""
    record = _get_result_or_404(result_id, container)
    start = datetime.combine(record.start_date, time.min)
    end = datetime.combine(record.end_date, time.max)
    items = container.news_repo.list_range(symbol, start, end)
    return [
        NewsMarkerOut(
            date=n.published_at.date().isoformat(),
            news_id=n.id,
            title=n.title,
            published_at=n.published_at.isoformat(),
            source=n.source,
            used=False,
        )
        for n in items
    ]


@router.get("/{result_id}/news/signal", response_model=list[NewsMarkerOut])
def get_backtest_news_signal(
    result_id: str, symbol: str, container: Container = Depends(get_container)
) -> list[NewsMarkerOut]:
    """ai.news_signal(newsstock-lib) 파이프라인이 참고하는 뉴스 클러스터를 마커로 반환한다.

    /news/used·/news/all은 data.news/NewsRepository(구 파이프라인, nemo_stock.db)만 알고
    ai.news_signal이 쓰는 별도 DB(newsstock.db)는 전혀 모르기 때문에, 워크플로가
    ai.news_signal만 쓰는 경우 기존 두 엔드포인트는 항상 빈 배열을 반환한다(버그) — 이 엔드포인트가
    그 데이터 소스를 대신 조회한다. 워크플로에 ai.news_signal 노드가 없으면 빈 배열.
    """
    record = _get_result_or_404(result_id, container)
    if symbol not in record.universe:
        raise HTTPException(status_code=400, detail="해당 백테스트의 대상 종목이 아닙니다.")

    workflow = container.workflow_repo.get(record.workflow_id)
    if workflow is None:
        return []
    graph = WorkflowGraph.from_dict(workflow.graph)
    node = next((n for n in graph.nodes.values() if n.type == "ai.news_signal"), None)
    if node is None:
        return []

    axis = str(node.params.get("axis", "종목"))
    key = str(node.params.get("key", "") or "")
    if axis == "종목" and not key:
        key = get_symbol_name(symbol) or ""
    if not key:
        return []

    period_days = int(node.params.get("period_days", 7) or 7)
    threshold = float(node.params.get("threshold", 0.1) or 0.1)
    decay_base = float(node.params.get("decay_base", 0.3) or 0.3)
    include_zero = bool(node.params.get("include_zero", True))
    decay_from = str(node.params.get("decay_from", "end") or "end")
    method_name = AXIS_METHOD.get(axis, "stock")

    # 노드는 매 거래일 start=그날, period=period_days(그날부터 앞으로 period_days)로 조회한다.
    # 백테스트 전체 표시 구간을 한 번에 커버하려면 start=백테스트 시작일, period=
    # (백테스트 기간 + 노드의 조회기간)으로 넓혀서 조회하면 각 거래일이 봤을 구간의 합집합을
    # 충분히 덮는다(경계 며칠 정도 더 넓게 잡히는 건 마커 표시 목적상 무해하다).
    span_days = (record.end_date - record.start_date).days + period_days

    trader = container.news_trader_factory(
        auto_update=False, threshold=threshold, decay_base=decay_base,
        include_zero=include_zero, decay_from=decay_from,
    )
    try:
        result = getattr(trader, method_name)(key, start=record.start_date.isoformat(), period=span_days)
    finally:
        trader.close()

    markers: list[NewsMarkerOut] = []
    for cluster in result.get("클러스터", []) or []:
        first_seen = str(cluster.get("최초발생날짜", ""))
        markers.append(
            NewsMarkerOut(
                date=first_seen[:10],
                news_id=str(cluster.get("클러스터id", "")),
                title=str(cluster.get("대표제목", "")),
                published_at=first_seen,
                source="newsstock",
                used=True,
            )
        )
    return markers
