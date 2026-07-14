"""공시(DART) 데이터 노드. 종목별 최근 공시 제목을 조회해 컨텍스트에 담는다."""

from __future__ import annotations

from app.dao.base import DisclosureRepository
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class DisclosureDataNode(Node):
    type = "data.disclosure"
    category = "data"
    display_name = "공시 데이터 조회"
    param_schema: list[NodeParam] = [
        {"key": "limit", "type": "number", "label": "조회 개수", "default": 3, "required": False},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        disclosure_repo = providers.get("disclosure_repo")
        if not isinstance(disclosure_repo, DisclosureRepository):
            raise RuntimeError("data.disclosure 노드 실행에는 disclosure_repo provider가 필요합니다.")

        limit = int(self.get_param("limit", 3))
        out = context.clone()
        for symbol in list(out.symbols.keys()):
            items = disclosure_repo.list_recent(symbol, limit=limit)
            if not items:
                out.symbols[symbol]["disclosure_text"] = ""
                out.symbols[symbol]["disclosure_id"] = None
                out.symbols[symbol]["disclosure_count"] = 0
                continue
            out.symbols[symbol]["disclosure_text"] = " / ".join(f"{i.corp_name} {i.report_nm}" for i in items)
            out.symbols[symbol]["disclosure_id"] = items[0].id
            out.symbols[symbol]["disclosure_count"] = len(items)
        return out
