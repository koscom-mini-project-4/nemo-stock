"""뉴스 데이터 노드. 종목별 최근 뉴스를 조회해 텍스트로 합쳐 컨텍스트에 담는다.

ai.sentiment_score 노드가 이 텍스트(news_text)와 캐시 키(news_id)를 사용한다.
"""

from __future__ import annotations

from app.dao.base import NewsRepository
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class NewsDataNode(Node):
    type = "data.news"
    category = "data"
    display_name = "뉴스 데이터 조회"
    param_schema: list[NodeParam] = [
        {"key": "limit", "type": "number", "label": "조회 개수", "default": 3, "required": False},
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        news_repo = providers.get("news_repo")
        if not isinstance(news_repo, NewsRepository):
            raise RuntimeError("data.news 노드 실행에는 news_repo provider가 필요합니다.")

        limit = int(self.get_param("limit", 3))
        out = context.clone()
        for symbol in list(out.symbols.keys()):
            items = news_repo.list_recent(symbol, limit=limit)
            if not items:
                out.symbols[symbol]["news_text"] = ""
                out.symbols[symbol]["news_id"] = None
                out.symbols[symbol]["news_count"] = 0
                continue
            out.symbols[symbol]["news_text"] = " / ".join(f"{i.title}: {i.body}" for i in items)
            out.symbols[symbol]["news_id"] = items[0].id
            out.symbols[symbol]["news_count"] = len(items)
        return out
