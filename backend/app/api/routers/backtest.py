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
    result_id: str, symbol: str, container: Container = Depends(get_container)
) -> list[PricePointOut]:
    record = _get_result_or_404(result_id, container)
    if symbol not in record.universe:
        raise HTTPException(status_code=400, detail="해당 백테스트의 대상 종목이 아닙니다.")
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
