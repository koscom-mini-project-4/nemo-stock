"""랭킹(상위 N) 필터 노드.

logic.if_else와 마찬가지로 필터형 노드다: 지정한 키 기준으로 정렬해 상위 N개 종목만
통과시키고, 나머지는 symbols에서 제거해 meta.filtered_out에 기록한다.
"""

from __future__ import annotations

from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class RankNode(Node):
    type = "logic.rank"
    category = "logic"
    display_name = "랭킹(상위 N)"
    description = (
        "params.key(symbols[code]의 키, 예: 'momentum_20')를 기준으로 내림차순(params.order="
        "'desc') 또는 오름차순('asc')으로 정렬해 상위 params.top_n개 종목만 통과시킨다. key 값이 "
        "없는 종목은 항상 탈락한다. 나머지는 logic.if_else와 동일하게 symbols에서 제거되고 "
        "meta.filtered_out에 기록된다. indicator.momentum 뒤에 연결해 상승률 상위 종목만 골라내는 "
        "횡단면 전략에 쓴다."
    )
    param_schema: list[NodeParam] = [
        {"key": "key", "type": "string", "label": "정렬 기준 키", "default": "momentum_20", "required": True},
        {"key": "top_n", "type": "number", "label": "상위 개수", "default": 3, "required": True},
        {
            "key": "order",
            "type": "select",
            "label": "정렬 순서",
            "default": "desc",
            "required": False,
            "options": ["desc", "asc"],
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        key = str(self.get_param("key", ""))
        top_n = int(self.get_param("top_n", 3))
        reverse = str(self.get_param("order", "desc")) != "asc"

        out = context.clone()
        original = out.symbols
        scored = [(symbol, data) for symbol, data in original.items() if key in data]
        scored.sort(key=lambda pair: pair[1][key], reverse=reverse)
        ranked = scored[:top_n]
        ranked_symbols = {symbol for symbol, _ in ranked}

        failed = [s for s in original if s not in ranked_symbols]
        out.symbols = {symbol: data for symbol, data in ranked}
        decisions: dict[str, dict] = {}
        for rank_idx, (symbol, data) in enumerate(ranked, start=1):
            data["rank"] = rank_idx
            decisions[symbol] = {
                "pass": True,
                "reason": f"{key}={data[key]} (상위 {rank_idx}/{top_n})",
            }
        for symbol in failed:
            if key in original[symbol]:
                decisions[symbol] = {"pass": False, "reason": f"{key}={original[symbol][key]} (순위 밖)"}
            else:
                decisions[symbol] = {"pass": False, "reason": f"'{key}' 값 없음"}
        out.meta.setdefault("filtered_out", {})[self.node_id] = failed
        out.meta.setdefault("decisions", {})[self.node_id] = decisions
        return out
