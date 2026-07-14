"""스케줄러 노드 — 모든 워크플로의 루트(진입) 노드.

실행 자체는 SchedulerService/트리거가 담당하며, 이 노드는 워크플로 실행 시작 시점에
대상 종목 유니버스를 NodeContext.symbols에 초기화하는 역할만 한다.
"""

from __future__ import annotations

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class SchedulerIntervalNode(Node):
    type = "scheduler.interval"
    category = "scheduler"
    display_name = "주기 스케줄러"
    param_schema: list[NodeParam] = [
        {"key": "interval_sec", "type": "number", "label": "실행 주기(초)", "default": 60, "required": True},
        {
            "key": "universe",
            "type": "string",
            "label": "대상 종목코드 (콤마 구분)",
            "default": "005930,000660",
            "required": True,
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        universe_raw = str(self.get_param("universe", ""))
        symbols = [s.strip() for s in universe_raw.split(",") if s.strip()]
        out = context.clone()
        for symbol in symbols:
            out.symbols.setdefault(symbol, {})
        out.meta["universe"] = symbols
        out.meta["interval_sec"] = self.get_param("interval_sec", 60)
        return out
