"""조건 분기(필터) 노드.

expr 파라미터는 종목별 데이터 dict를 이름공간으로 하는 표현식이다.
예) "volume_ratio > 2.0", "price > ma_5"
조건을 만족하지 못하는 종목은 이후 노드로 전달되지 않는다(필터링).
"""

from __future__ import annotations

from simpleeval import EvalWithCompoundTypes

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class IfElseNode(Node):
    type = "logic.if_else"
    category = "logic"
    display_name = "IF 조건"
    param_schema: list[NodeParam] = [
        {"key": "expr", "type": "expression", "label": "조건식", "default": "True", "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        expr = str(self.get_param("expr", "True"))
        out = context.clone()
        passed: dict[str, dict] = {}
        failed: list[str] = []
        for symbol, data in out.symbols.items():
            evaluator = EvalWithCompoundTypes(names=dict(data))
            try:
                result = bool(evaluator.eval(expr))
            except Exception as exc:  # noqa: BLE001 - 조건식 오류는 해당 종목 탈락으로 처리
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                result = False
            if result:
                passed[symbol] = data
            else:
                failed.append(symbol)
        out.symbols = passed
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        return out
