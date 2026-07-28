"""손절 필터 노드. 보유 중인 종목의 평단가 대비 손실률이 기준을 넘으면 통과시킨다."""

from __future__ import annotations

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class StopLossNode(Node):
    type = "risk.stop_loss"
    category = "risk"
    display_name = "손절"
    description = (
        "보유 중인 종목(symbols[code].held_qty > 0, 엔진이 자동 주입) 중 평단가"
        "(held_avg_price) 대비 현재가(price)의 손실률이 params.loss_pct 이상인 종목만 통과시키고 "
        "나머지는 제거한다(logic.if_else와 동일한 필터형 노드). data.price 노드가 이 노드보다 "
        "앞에 있어야 한다. 통과한 종목 뒤에 side=sell인 execution.market_order를 연결하면 "
        "손절 매도가 된다."
    )
    param_schema: list[NodeParam] = [
        {"key": "loss_pct", "type": "number", "label": "손절 기준 손실률(%)", "default": 5.0, "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        loss_pct = float(self.get_param("loss_pct", 5.0))
        out = context.clone()

        passed: dict[str, dict] = {}
        failed: list[str] = []
        for symbol, data in out.symbols.items():
            held_qty = data.get("held_qty", 0)
            held_avg_price = data.get("held_avg_price", 0.0)
            price = data.get("price")
            if held_qty > 0 and price is not None and held_avg_price > 0:
                pnl_pct = (price - held_avg_price) / held_avg_price * 100
                if pnl_pct <= -loss_pct:
                    passed[symbol] = data
                    continue
            failed.append(symbol)

        out.symbols = passed
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        return out
