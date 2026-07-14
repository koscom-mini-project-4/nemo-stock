from __future__ import annotations

from datetime import date, timedelta

from app.backtest.metrics import compute_metrics
from app.broker.base import OrderResult


def _dates(n: int) -> list[date]:
    start = date(2025, 1, 1)
    return [start + timedelta(days=i) for i in range(n)]


def test_compute_metrics_flat_equity_curve_has_zero_return():
    days = _dates(5)
    curve = [(d, 1_000_000.0) for d in days]
    metrics = compute_metrics(curve, [], initial_capital=1_000_000.0)
    assert metrics.total_return_pct == 0.0
    assert metrics.mdd_pct == 0.0
    assert metrics.trade_count == 0
    assert metrics.win_rate_pct == 0.0


def test_compute_metrics_growth_and_drawdown():
    days = _dates(4)
    curve = list(zip(days, [1_000_000.0, 1_200_000.0, 900_000.0, 1_100_000.0]))
    metrics = compute_metrics(curve, [], initial_capital=1_000_000.0)
    assert metrics.total_return_pct == 10.0
    # peak 1.2M -> trough 0.9M => drawdown 25%
    assert metrics.mdd_pct == 25.0


def test_compute_metrics_win_rate_and_profit_loss_ratio():
    days = _dates(2)
    curve = [(days[0], 1_000_000.0), (days[1], 1_050_000.0)]
    orders = [
        OrderResult(
            order_id="o1", symbol="005930", side="buy", order_type="market", qty=10, price=1000,
            status="filled", filled_at=None,
        ),
        OrderResult(
            order_id="o2", symbol="005930", side="sell", order_type="market", qty=10, price=1100,
            status="filled", filled_at=None, realized_pnl=1000.0,
        ),
        OrderResult(
            order_id="o3", symbol="000660", side="sell", order_type="market", qty=5, price=900,
            status="filled", filled_at=None, realized_pnl=-500.0,
        ),
    ]
    metrics = compute_metrics(curve, orders, initial_capital=1_000_000.0)
    assert metrics.trade_count == 2
    assert metrics.win_rate_pct == 50.0
    assert metrics.profit_loss_ratio == 2.0  # avg_win(1000) / avg_loss(500)


def test_compute_metrics_empty_curve_returns_zeroed_metrics():
    metrics = compute_metrics([], [], initial_capital=1_000_000.0)
    assert metrics.total_return_pct == 0.0
    assert metrics.trade_count == 0
    assert metrics.profit_loss_ratio is None
