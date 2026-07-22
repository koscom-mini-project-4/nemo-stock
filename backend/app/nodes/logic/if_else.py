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
    description = (
        "조건 분기(필터). params.expr는 symbols[code]의 키를 변수로 쓰는 표현식이다(예: "
        "'volume_ratio > 2.0', 'price > ma_5'). expr가 False이거나 필요한 키가 symbols[code]에 "
        "없어 평가 오류가 나면 해당 종목을 symbols에서 제거하고(이후 노드로 전달 안 함) "
        "meta.filtered_out에 기록한다. 새 데이터를 추가하지 않고 종목 집합만 걸러낸다. "
        "held_qty(보유수량)/held_avg_price(평단가)/cash(현금)/equity(평가자산)는 어느 노드도 "
        "배선하지 않아도 엔진이 런 시작 시점에 자동으로 채워주므로 expr에서 바로 참조 가능하다 "
        "(예: 'held_qty == 0 and cash > price * 10')."
    )
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
