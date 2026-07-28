"""동일비중 배분 노드. 통과한 종목들에게 현금을 균등 배분해 매수 수량을 계산한다."""

from __future__ import annotations

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class EqualWeightNode(Node):
    type = "portfolio.equal_weight"
    category = "portfolio"
    display_name = "동일비중 배분"
    description = (
        "이 노드를 통과한 종목들에게 현금(symbols[code].cash, 엔진이 자동 주입)의 "
        "params.allocation_ratio 비율을 종목 수만큼 균등 배분해 매수 수량을 계산한다. "
        "data.price 노드가 이 노드보다 앞에 있어야 한다(symbols[code].price 필요). 출력: "
        "symbols[code]에 'target_qty'(정수, 종목당 배분 수량)를 채운다. execution.market_order "
        "노드가 target_qty가 있으면 params.qty 대신 이 값을 사용한다 — 이 노드를 "
        "execution.market_order 앞에 연결하면 동적 비중 배분 매수가 된다."
    )
    param_schema: list[NodeParam] = [
        {
            "key": "allocation_ratio",
            "type": "number",
            "label": "전체 배분 비율(현금 대비)",
            "default": 0.9,
            "required": True,
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        allocation_ratio = float(self.get_param("allocation_ratio", 0.9))
        out = context.clone()
        n = len(out.symbols)
        if n == 0:
            return out

        for symbol, data in out.symbols.items():
            price = data.get("price")
            cash = data.get("cash", 0.0)
            if not price or price <= 0:
                data["target_qty"] = 0
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: price 없음, 배분 스킵")
                continue
            budget = cash * allocation_ratio / n
            data["target_qty"] = int(budget // price)
        return out
