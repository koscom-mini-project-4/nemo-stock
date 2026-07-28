"""노드 패키지.

load_all_nodes()를 호출하면 모든 내장 노드 모듈이 import되어
app.nodes.base.NODE_REGISTRY에 등록된다.
"""

from __future__ import annotations


def load_all_nodes() -> None:
    from app.nodes import scheduler  # noqa: F401
    from app.nodes.ai import sentiment_score  # noqa: F401
    from app.nodes.data import disclosure, news, price  # noqa: F401
    from app.nodes.execution import market_order  # noqa: F401
    from app.nodes.indicator import momentum, moving_average, rsi  # noqa: F401
    from app.nodes.logic import if_else, rank  # noqa: F401
    from app.nodes.portfolio import equal_weight  # noqa: F401
    from app.nodes.risk import max_position, stop_loss  # noqa: F401
