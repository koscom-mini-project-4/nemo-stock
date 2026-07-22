"""공시(DART) 데이터 노드. 종목별 최근 공시 제목을 조회해 컨텍스트에 담는다."""

from __future__ import annotations

from app.dao.base import DisclosureRepository
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class DisclosureDataNode(Node):
    type = "data.disclosure"
    category = "data"
    display_name = "공시 데이터 조회"
    description = (
        "종목별 최근 공시(DART) 제목 params.limit건을 조회한다. 출력: symbols[code]에 "
        "disclosure_text(회사명+공시제목 합침)/disclosure_id(최신 공시 id)/disclosure_count를 "
        "채운다. ai.sentiment_score 노드(params.source=disclosure)가 disclosure_text/"
        "disclosure_id를 입력으로 사용하므로, 감성 점수화를 하려면 이 노드를 "
        "ai.sentiment_score보다 앞에 연결해야 한다."
    )
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
