"""수집 시점 뉴스 신호 적재.

크롤러/외부 AI가 정제한 분류(Depth 1/2/3)를 받아 충격량(Impact)을 계산해 NewsSignalRecord로
저장한다. 분류가 아직 없으면 AIClient로 즉석 분류할 수도 있다(best-effort). 실제 서비스에서는
이 지점이 비동기 파이프라인(예: AMQP) + Transactional Outbox의 소비자 쪽에 해당한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.ai.base import AIClient
from app.ai.news_classify import classify_news, normalize_classification
from app.dao.base import NewsSignalRecord
from app.news_signals.impact import compute_impact


def build_news_signal(
    classification: dict,
    published_at: datetime,
    *,
    news_id: str | None = None,
    symbol: str | None = None,
    source: str = "manual",
) -> NewsSignalRecord:
    """정규화 → 충격량 계산 → NewsSignalRecord 생성(저장은 호출자가)."""
    norm = normalize_classification(classification)
    impact = compute_impact(norm)
    return NewsSignalRecord(
        id=news_id or str(uuid.uuid4()),
        symbol=symbol,
        sector=norm["depth_2"]["target_sector"],
        direction=norm["depth_1"]["direction"],
        event_type=norm["depth_3"]["event_type"],
        themes=norm["depth_3"]["themes"],
        base_impact=impact["base_impact"],
        sector_score=impact["sector_score"],
        domestic_score=impact["domestic_score"],
        overseas_score=impact["overseas_score"],
        published_at=published_at,
        source=source,
    )


def classify_and_build_signal(
    ai_client: AIClient,
    text: str,
    published_at: datetime,
    *,
    news_id: str | None = None,
    symbol: str | None = None,
    source: str = "manual",
) -> NewsSignalRecord:
    """원문 텍스트를 AI로 분류한 뒤 신호를 만든다(AI 키가 있을 때만)."""
    classification = classify_news(ai_client, text)
    return build_news_signal(
        classification, published_at, news_id=news_id, symbol=symbol, source=source
    )
