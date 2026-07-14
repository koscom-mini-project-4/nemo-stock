"""시장가 주문 실행 노드 (더미/실 브로커 공용 인터페이스 사용)."""

from __future__ import annotations

from app.broker.base import OrderExecutionProvider, OrderRequest
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class MarketOrderNode(Node):
    type = "execution.market_order"
    category = "execution"
    display_name = "시장가 주문"
    param_schema: list[NodeParam] = [
        {
            "key": "side",
            "type": "select",
            "label": "매매 구분",
            "default": "buy",
            "required": True,
            "options": ["buy", "sell"],
        },
        {"key": "qty", "type": "number", "label": "주문 수량(종목당)", "default": 1, "required": True},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        broker = providers.get("broker")
        if not isinstance(broker, OrderExecutionProvider):
            raise RuntimeError("execution.market_order 노드 실행에는 broker provider가 필요합니다.")

        side = str(self.get_param("side", "buy"))
        qty = int(self.get_param("qty", 1))

        out = context.clone()
        orders: list[dict] = []
        for symbol, data in out.symbols.items():
            ref_price = data.get("price")
            if ref_price is None:
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: 기준가(price) 없음, 주문 스킵")
                continue
            result = broker.place_order(
                OrderRequest(
                    run_id=context.run_id,
                    symbol=symbol,
                    side=side,  # type: ignore[arg-type]
                    order_type="market",
                    qty=qty,
                    ref_price=ref_price,
                )
            )
            data["order_status"] = result.status
            data["order_price"] = result.price
            orders.append(
                {
                    "order_id": result.order_id,
                    "symbol": symbol,
                    "side": result.side,
                    "qty": result.qty,
                    "price": result.price,
                    "status": result.status,
                    "reason": result.reason,
                }
            )
        out.meta.setdefault("orders", []).extend(orders)
        return out
