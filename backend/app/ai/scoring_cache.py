"""AI 점수화 + 캐싱 공통 모듈.

뉴스/공시 감성 점수화는 동일한 캐시 전략을 공유한다: (subject_type, subject_id,
prompt_version, model) 키로 조회해 캐시 히트 시 AI를 호출하지 않는다.
prompt_version을 올리면 캐시가 자동으로 무효화된다(새 버전 키로 재계산).
"""

from __future__ import annotations

import uuid

from app.ai.base import AIClient
from app.dao.base import AIScoreCacheRecord, AIScoreCacheRepository

PROMPT_VERSION = "v1"

_SENTIMENT_SYSTEM_PROMPT = (
    "당신은 한국 주식시장 뉴스/공시 문구를 분석하는 애널리스트입니다. "
    "입력된 텍스트가 해당 종목의 주가에 미칠 영향을 -100(매우 부정적)에서 100(매우 긍정적) 사이의 "
    "정수 점수로 평가하고, 근거를 한 문장으로 요약하세요. "
    '반드시 다음 JSON 형식으로만 응답하세요: {"score": number, "summary": string}'
)


def get_or_compute_sentiment_score(
    cache_repo: AIScoreCacheRepository,
    ai_client: AIClient,
    subject_type: str,
    subject_id: str,
    text: str,
) -> dict:
    """캐시에 있으면 그대로 반환하고, 없으면 AI를 호출해 계산 후 캐시에 저장한다."""
    model = ai_client.model_name
    cached = cache_repo.get(subject_type, subject_id, PROMPT_VERSION, model)
    if cached is not None:
        return cached.score_json

    raw = ai_client.complete_json(_SENTIMENT_SYSTEM_PROMPT, text, purpose="sentiment_score")
    score_json = {
        "score": float(raw.get("score", 0)),
        "summary": str(raw.get("summary", "")),
    }
    cache_repo.save(
        AIScoreCacheRecord(
            id=str(uuid.uuid4()),
            subject_type=subject_type,
            subject_id=subject_id,
            prompt_version=PROMPT_VERSION,
            model=model,
            score_json=score_json,
        )
    )
    return score_json
