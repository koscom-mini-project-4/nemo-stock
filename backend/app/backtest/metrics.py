"""백테스트 성과/위험 지표 계산."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from app.broker.base import OrderResult


@dataclass
class BacktestMetrics:
    total_return_pct: float
    cagr_pct: float
    mdd_pct: float
    volatility_pct: float
    win_rate_pct: float
    profit_loss_ratio: float | None
    trade_count: int


def compute_metrics(
    equity_curve: list[tuple[date, float]],
    orders: list[OrderResult],
    initial_capital: float,
) -> BacktestMetrics:
    if not equity_curve or initial_capital <= 0:
        return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0.0, None, 0)

    final_equity = equity_curve[-1][1]
    total_return = (final_equity - initial_capital) / initial_capital

    days = max((equity_curve[-1][0] - equity_curve[0][0]).days, 1)
    years = days / 365.0
    if final_equity > 0 and years > 0:
        cagr = (final_equity / initial_capital) ** (1 / years) - 1
    else:
        cagr = -1.0

    max_dd = 0.0
    peak = equity_curve[0][1]
    for _, equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    daily_returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        cur = equity_curve[i][1]
        if prev:
            daily_returns.append((cur - prev) / prev)
    if len(daily_returns) > 1:
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        volatility = math.sqrt(variance) * math.sqrt(252)
    else:
        volatility = 0.0

    sell_trades = [o for o in orders if o.side == "sell" and o.status == "filled" and o.realized_pnl is not None]
    trade_count = len(sell_trades)
    wins = [t for t in sell_trades if (t.realized_pnl or 0) > 0]
    losses = [t for t in sell_trades if (t.realized_pnl or 0) < 0]
    win_rate = (len(wins) / trade_count * 100) if trade_count else 0.0

    profit_loss_ratio: float | None = None
    if wins and losses:
        avg_win = sum(t.realized_pnl for t in wins) / len(wins)  # type: ignore[misc]
        avg_loss = abs(sum(t.realized_pnl for t in losses) / len(losses))  # type: ignore[misc]
        profit_loss_ratio = round(avg_win / avg_loss, 3) if avg_loss else None

    return BacktestMetrics(
        total_return_pct=round(total_return * 100, 3),
        cagr_pct=round(cagr * 100, 3),
        mdd_pct=round(max_dd * 100, 3),
        volatility_pct=round(volatility * 100, 3),
        win_rate_pct=round(win_rate, 3),
        profit_loss_ratio=profit_loss_ratio,
        trade_count=trade_count,
    )
