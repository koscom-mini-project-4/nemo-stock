"""시장가 주문 실행 노드 (더미/실 브로커 공용 인터페이스 사용)."""

from __future__ import annotations

from app.broker.base import OrderExecutionProvider, OrderRequest
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class MarketOrderNode(Node):
    type = "execution.market_order"
    category = "execution"
    display_name = "시장가 주문"
    description = (
        "각 종목에 대해 broker provider로 시장가 주문을 넣는다. 입력: symbols[code].price를 "
        "기준가로 사용(없으면 해당 종목 주문 스킵 후 meta.errors에 기록). 수량 결정 우선순위: "
        "1) symbols[code].target_qty(portfolio.equal_weight 등 앞선 노드가 계산한 동적 수량) "
        "2) params.qty_mode='가능수량 비율(%)'이면 매수는 symbols[code].cash/기준가*qty_pct/100, "
        "매도는 symbols[code].held_qty*qty_pct/100(둘 다 엔진이 자동 주입하는 필드) "
        "3) params.qty(고정 수량). params.side(buy|sell). "
        "출력: symbols[code]에 order_status/order_price, meta.orders에 주문 상세"
        "(order_id/symbol/side/qty/price/status/reason) 누적. 수량이 0 이하이면 주문을 스킵한다."
    )
    param_schema: list[NodeParam] = [
        {
            "key": "side",
            "type": "select",
            "label": "매매 구분",
            "default": "buy",
            "required": True,
            "options": ["buy", "sell"],
        },
        {
            "key": "qty_mode",
            "type": "select",
            "label": "수량 결정 방식",
            "default": "고정수량",
            "required": False,
            "options": ["고정수량", "가능수량 비율(%)"],
        },
        {
            "key": "qty",
            "type": "number",
            "label": "주문 수량(종목당, target_qty 없을 때 사용)",
            "default": 1,
            "required": True,
            "show_if": {"param": "qty_mode", "equals": "고정수량"},
        },
        {
            "key": "qty_pct",
            "type": "number",
            "label": "주문 가능수량의 비율(%)",
            "default": 50,
            "required": False,
            "show_if": {"param": "qty_mode", "equals": "가능수량 비율(%)"},
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        broker = providers.get("broker")
        if not isinstance(broker, OrderExecutionProvider):
            raise RuntimeError("execution.market_order 노드 실행에는 broker provider가 필요합니다.")

        side = str(self.get_param("side", "buy"))
        qty_mode = str(self.get_param("qty_mode", "고정수량"))
        default_qty = int(self.get_param("qty", 1))
        qty_pct = float(self.get_param("qty_pct", 50))

        out = context.clone()
        orders: list[dict] = []
        for symbol, data in out.symbols.items():
            ref_price = data.get("price")
            if ref_price is None:
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: 기준가(price) 없음, 주문 스킵")
                continue
            if data.get("target_qty") is not None:
                qty = int(data["target_qty"])
            elif qty_mode == "가능수량 비율(%)":
                if side == "sell":
                    qty = int(float(data.get("held_qty", 0)) * qty_pct / 100)
                else:
                    qty = int(float(data.get("cash", 0)) / ref_price * qty_pct / 100) if ref_price else 0
            else:
                qty = default_qty
            if qty <= 0:
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
