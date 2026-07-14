"""노드 패키지.

load_all_nodes()를 호출하면 모든 내장 노드 모듈이 import되어
app.nodes.base.NODE_REGISTRY에 등록된다.
"""

from __future__ import annotations


def load_all_nodes() -> None:
    from app.nodes import scheduler  # noqa: F401
    from app.nodes.data import price  # noqa: F401
    from app.nodes.execution import market_order  # noqa: F401
    from app.nodes.indicator import moving_average  # noqa: F401
    from app.nodes.logic import if_else  # noqa: F401
