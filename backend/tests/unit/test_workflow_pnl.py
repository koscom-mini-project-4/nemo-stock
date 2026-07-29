from datetime import datetime

from app.dao.base import NodeEventRecord, RunRecord
from app.workflow.pnl import compute_workflow_pnl, load_workflow_fills


def _order(order_id: str, symbol: str, side: str, qty: float, price: float, status: str = "filled") -> dict:
    return {"order_id": order_id, "symbol": symbol, "side": side, "qty": qty, "price": price, "status": status}


def _event(run_id: str, node_id: str, ts: datetime, orders: list[dict]) -> NodeEventRecord:
    return NodeEventRecord(
        id=f"evt-{node_id}",
        run_id=run_id,
        node_id=node_id,
        node_type="execution.market_order",
        status="success",
        timestamp=ts,
        output_json={"symbols": {}, "meta": {"orders": orders}},
    )


def test_compute_workflow_pnl_realized_gain_on_full_sell():
    fills = [
        _order("o1", "005930", "buy", 10, 1000),
        _order("o2", "005930", "sell", 10, 1200),
    ]
    result = compute_workflow_pnl("wf1", fills, current_price=lambda s: 1200)

    assert result.realized_pnl == 2000
    assert result.unrealized_pnl == 0
    assert result.total_pnl == 2000
    assert result.total_invested == 10000
    assert result.return_pct == 20.0
    assert result.trade_count == 2


def test_compute_workflow_pnl_unrealized_on_open_position():
    fills = [_order("o1", "005930", "buy", 10, 1000)]
    result = compute_workflow_pnl("wf1", fills, current_price=lambda s: 1100)

    assert result.realized_pnl == 0
    assert result.unrealized_pnl == 1000
    assert result.total_pnl == 1000
    assert result.return_pct == 10.0


def test_compute_workflow_pnl_no_fills_returns_none_pct():
    result = compute_workflow_pnl("wf1", [], current_price=lambda s: 1000)

    assert result.total_invested == 0
    assert result.total_pnl == 0
    assert result.return_pct is None
    assert result.trade_count == 0


def test_compute_workflow_pnl_ignores_rejected_and_unfilled_orders():
    fills = [
        _order("o1", "005930", "buy", 10, 1000, status="rejected"),
        _order("o2", "005930", "buy", 5, 1000, status="filled"),
    ]
    result = compute_workflow_pnl("wf1", fills, current_price=lambda s: 1000)

    assert result.trade_count == 1
    assert result.total_invested == 5000


def test_load_workflow_fills_dedupes_and_filters_backtest_and_other_workflows():
    runs = [
        RunRecord(id="r-live", workflow_id="wf1", mode="live", status="success", started_at=datetime(2026, 1, 1)),
        RunRecord(id="r-test", workflow_id="wf1", mode="test", status="success", started_at=datetime(2026, 1, 2)),
        RunRecord(
            id="r-backtest", workflow_id="wf1", mode="backtest", status="success", started_at=datetime(2026, 1, 3)
        ),
        RunRecord(id="r-other", workflow_id="wf2", mode="live", status="success", started_at=datetime(2026, 1, 1)),
    ]
    events_by_run = {
        "r-live": [_event("r-live", "n1", datetime(2026, 1, 1, 9), [_order("o1", "005930", "buy", 10, 1000)])],
        "r-test": [
            # o1 재등장(같은 order_id) — 다운스트림 노드가 meta를 그대로 이어받아 중복 노출되는 경우를 흉내
            _event(
                "r-test",
                "n1",
                datetime(2026, 1, 2, 9),
                [_order("o1", "005930", "buy", 10, 1000), _order("o2", "005930", "sell", 5, 1200)],
            )
        ],
        "r-backtest": [_event("r-backtest", "n1", datetime(2026, 1, 3, 9), [_order("o3", "005930", "buy", 99, 1)])],
        "r-other": [_event("r-other", "n1", datetime(2026, 1, 1, 9), [_order("o4", "000660", "buy", 1, 1)])],
    }

    fills = load_workflow_fills("wf1", runs, lambda run_id: events_by_run[run_id])

    assert [f["order_id"] for f in fills] == ["o1", "o2"]
