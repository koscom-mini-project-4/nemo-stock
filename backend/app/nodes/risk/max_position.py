"""종목당 최대 비중 제한 노드. portfolio 노드가 계산한 target_qty를 상한 이하로 축소한다."""

from __future__ import annotations

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class MaxPositionNode(Node):
    type = "risk.max_position"
    category = "risk"
    display_name = "종목당 최대 비중 제한"
    description = (
        "portfolio.equal_weight 등이 계산한 symbols[code].target_qty가 종목당 최대 비중"
        "(params.max_weight, 전체 평가자산(equity, 엔진이 자동 주입) 대비)을 넘지 않도록 "
        "줄인다. target_qty가 없는 종목은 건드리지 않는다(0으로 취급하지 않음). "
        "portfolio.equal_weight 뒤, execution.market_order 앞에 연결한다."
    )
    param_schema: list[NodeParam] = [
        {
            "key": "max_weight",
            "type": "number",
            "label": "종목당 최대 비중(평가자산 대비, 0~1)",
            "default": 0.3,
            "required": True,
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        max_weight = float(self.get_param("max_weight", 0.3))
        out = context.clone()

        for symbol, data in out.symbols.items():
            target_qty = data.get("target_qty")
            price = data.get("price")
            equity = data.get("equity", 0.0)
            if target_qty is None or not price or price <= 0 or equity <= 0:
                continue
            max_qty = int((equity * max_weight) // price)
            if target_qty > max_qty:
                data["target_qty"] = max_qty
        return out
