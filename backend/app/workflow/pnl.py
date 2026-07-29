"""워크플로(전략)별 실거래 체결 이력 기반 손익 집계.

계좌가 전략별로 분리되지 않은 단일 공용 포트폴리오(app/broker/persistent_dummy.py)라
"전략별 손익"을 정확히 나눌 원장이 없다. 대신 해당 워크플로 자신의 run(live/test)들이
남긴 체결 기록(execution.market_order 노드가 meta.orders에 쌓는 값)만으로 평단가를 별도
추적해 근사 손익을 계산한다 — 같은 종목을 여러 전략이 함께 매매하면 이 값은 근사치다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from app.dao.base import NodeEventRecord, RunRecord

# live/test 두 모드만 실제 공용 포트폴리오(PersistentOrderExecutionProvider)에 체결을 남긴다.
# backtest는 별도 가상 실행(DummyOrderExecutionProvider)이라 이 집계에서 제외한다.
_ATTRIBUTABLE_MODES = {"live", "test"}


@dataclass
class WorkflowPnl:
    workflow_id: str
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_invested: float
    return_pct: float | None
    trade_count: int


def load_workflow_fills(
    workflow_id: str,
    runs: Iterable[RunRecord],
    events_by_run: Callable[[str], list[NodeEventRecord]],
) -> list[dict]:
    """workflow_id의 live/test run들에서 체결 주문을 시간순으로, order_id 기준 중복 제거해 모은다."""
    relevant_runs = sorted(
        (r for r in runs if r.workflow_id == workflow_id and r.mode in _ATTRIBUTABLE_MODES),
        key=lambda r: r.started_at,
    )
    seen: set[str] = set()
    fills: list[dict] = []
    for run in relevant_runs:
        events = sorted(events_by_run(run.id), key=lambda e: e.timestamp)
        for event in events:
            if not event.output_json:
                continue
            for order in event.output_json.get("meta", {}).get("orders", []):
                order_id = order.get("order_id")
                if not order_id or order_id in seen:
                    continue
                seen.add(order_id)
                fills.append(order)
    return fills


def compute_workflow_pnl(
    workflow_id: str,
    fills: list[dict],
    current_price: Callable[[str], float | None],
) -> WorkflowPnl:
    """fills(시간순 체결 목록)로부터 이동평균 방식 평단가를 자체 추적해 실현+평가손익을 계산한다."""
    qty_by_symbol: dict[str, float] = {}
    avg_by_symbol: dict[str, float] = {}
    realized_pnl = 0.0
    total_invested = 0.0
    trade_count = 0

    for fill in fills:
        if fill.get("status") != "filled":
            continue
        symbol = fill.get("symbol")
        qty = float(fill.get("qty") or 0)
        price = float(fill.get("price") or 0)
        if not symbol or qty <= 0:
            continue
        trade_count += 1
        held_qty = qty_by_symbol.get(symbol, 0.0)
        held_avg = avg_by_symbol.get(symbol, 0.0)

        if fill.get("side") == "buy":
            cost = price * qty
            total_invested += cost
            new_qty = held_qty + qty
            avg_by_symbol[symbol] = (held_avg * held_qty + cost) / new_qty if new_qty else 0.0
            qty_by_symbol[symbol] = new_qty
        else:
            # 이 워크플로가 실제로 산 적 있는 수량까지만 손익에 반영한다(근사).
            sell_qty = min(qty, held_qty)
            realized_pnl += (price - held_avg) * sell_qty
            qty_by_symbol[symbol] = held_qty - sell_qty

    unrealized_pnl = 0.0
    for symbol, qty in qty_by_symbol.items():
        if qty <= 0:
            continue
        price = current_price(symbol)
        if price is None:
            continue
        unrealized_pnl += (price - avg_by_symbol[symbol]) * qty

    total_pnl = realized_pnl + unrealized_pnl
    return_pct = (total_pnl / total_invested * 100) if total_invested > 0 else None

    return WorkflowPnl(
        workflow_id=workflow_id,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=total_pnl,
        total_invested=total_invested,
        return_pct=return_pct,
        trade_count=trade_count,
    )
