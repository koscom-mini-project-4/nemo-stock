"""Phase 1 — 단일 뉴스 충격량(Impact) 계산.

AI가 뱉어준 이산형 라벨(direction 1/0/-1, event_type Enum, Depth 2 boolean)에 시장 파급력
가중치를 곱해, 뉴스 1건이 발생시키는 '에너지' 점수를 창조한다. 결과는 수집 시점에
NewsSignalRecord로 저장되고, 이후 aggregate.py가 섹터·기간으로 집계한다.

    Base Impact  = direction × Event Weight
    sector_score = Base Impact  (is_sector_impact == True 일 때, 아니면 0)
    ... (domestic/overseas 동일)
"""

from __future__ import annotations

from app.ai.news_classify import DEFAULT_EVENT_TYPE

# 각 이벤트가 시장에 미치는 파급력 상수. 향후 DB 메타 테이블로 이관 가능.
EVENT_WEIGHTS: dict[str, float] = {
    "Geopolitical_Risk": 1.8,   # 전쟁, 관세 — 가장 강한 파급력
    "Macro_Indicator": 1.5,     # 금리, CPI
    "M&A_Investment": 1.5,      # 인수합병, 투자
    "Earnings_Contract": 1.2,   # 실적, 수주
    "Management_Risk": 1.5,     # 횡령·경영진 리스크(악재 시 킬스위치로 강하게 작용)
    "Policy_Regulation": 1.0,   # 정책, 규제
    "General_Market": 0.3,      # 단순 시황 — 노이즈 감가상각
}


def event_weight(event_type: str) -> float:
    """이벤트 가중치를 반환한다(미정의 이벤트는 General_Market 가중치로 폴백)."""
    return EVENT_WEIGHTS.get(event_type, EVENT_WEIGHTS[DEFAULT_EVENT_TYPE])


def compute_impact(classification: dict) -> dict:
    """정규화된 분류(Depth 1/2/3)로부터 충격량 점수를 계산한다.

    반환: base_impact, sector_score, domestic_score, overseas_score.
    입력은 app.ai.news_classify.normalize_classification()을 통과한 dict라고 가정한다.
    """
    direction = int(classification["depth_1"]["direction"])
    d2 = classification["depth_2"]
    event_type = str(classification["depth_3"]["event_type"])

    base = direction * event_weight(event_type)
    return {
        "base_impact": base,
        "sector_score": base if d2.get("is_sector_impact") else 0.0,
        "domestic_score": base if d2.get("is_domestic_impact") else 0.0,
        "overseas_score": base if d2.get("is_overseas_impact") else 0.0,
    }
