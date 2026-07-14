"""AI 감성 점수화 노드. data.news 또는 data.disclosure 노드 이후에 연결해 사용한다.

AIScoreCacheRepository를 통해 (subject_type, subject_id) 기준으로 캐싱되므로
동일한 뉴스/공시에 대해서는 AI를 다시 호출하지 않는다.
"""

from __future__ import annotations

from app.ai.base import AIClient
from app.ai.scoring_cache import get_or_compute_sentiment_score
from app.dao.base import AIScoreCacheRepository
from app.nodes.base import Node, NodeContext, NodeParam, register_node


@register_node
class SentimentScoreNode(Node):
    type = "ai.sentiment_score"
    category = "ai"
    display_name = "감성 점수화 (AI)"
    param_schema: list[NodeParam] = [
        {
            "key": "source",
            "type": "select",
            "label": "분석 대상",
            "default": "news",
            "required": True,
            "options": ["news", "disclosure"],
        },
    ]

    def execute(self, context: NodeContext, **providers: object) -> NodeContext:
        ai_client = providers.get("ai_client")
        cache_repo = providers.get("ai_score_cache_repo")
        if not isinstance(ai_client, AIClient) or not isinstance(cache_repo, AIScoreCacheRepository):
            raise RuntimeError("ai.sentiment_score 노드 실행에는 ai_client/ai_score_cache_repo provider가 필요합니다.")

        source = str(self.get_param("source", "news"))
        text_field = f"{source}_text"
        id_field = f"{source}_id"

        out = context.clone()
        for symbol, data in out.symbols.items():
            text = data.get(text_field)
            subject_id = data.get(id_field)
            if not text or not subject_id:
                data["sentiment_score"] = None
                data["sentiment_summary"] = None
                continue
            try:
                result = get_or_compute_sentiment_score(
                    cache_repo=cache_repo,
                    ai_client=ai_client,
                    subject_type=source,
                    subject_id=str(subject_id),
                    text=text,
                )
                data["sentiment_score"] = result["score"]
                data["sentiment_summary"] = result["summary"]
            except Exception as exc:  # noqa: BLE001 - AI 오류는 해당 종목 점수 없음으로 처리
                out.meta.setdefault("errors", []).append(f"{self.node_id}:{symbol}: {exc}")
                data["sentiment_score"] = None
                data["sentiment_summary"] = None
        return out
