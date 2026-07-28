"""금융 뉴스 분류(Depth 1/2/3) + 캐싱 공통 모듈.

`ai.sentiment_score`와 동일한 캐시 전략을 공유한다: (subject_type, subject_id,
prompt_version, model) 키로 조회해 캐시 히트 시 AI를 다시 호출하지 않는다.
sentiment와 캐시 키가 충돌하지 않도록 subject_type="news_classify" 네임스페이스를 쓴다.

AI가 반환한 JSON은 신뢰할 수 없으므로 normalize_classification()으로 항상 정규화한다
(direction ∈ {-1,0,1}, event_type ∈ EVENT_TYPES, themes ≤ 2개). 매매 엔진이 그대로
파싱할 수 있는 안정적인 구조를 보장한다.

koscom_nemonemo(fork)에서 포트(DESIGN.md §0-6). classify_news()가 complete_json()에
purpose="news_classify"를 넘기도록 한 줄만 수정했다(관리자 페이지 사용량 통계의 목적별
집계용, app/ai/openai_client.py 참조) — 그 외 로직은 원본 그대로다.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.ai.base import AIClient
from app.dao.base import AIScoreCacheRecord, AIScoreCacheRepository
from app.news_signals.sectors import normalize_sector, sector_prompt_block
from app.news_signals.themes import normalize_themes, theme_prompt_block

# v4: 비경제 뉴스 게이트 규칙 + Non_Economic(경제 무관) 이벤트 타입 추가(2026-07-19).
PROMPT_VERSION = "v4"

SUBJECT_TYPE = "news_classify"

# 이벤트 성격 Enum(허용 값). AI가 이 외 값을 반환하면 "General_Market"으로 강등한다.
EVENT_TYPES = (
    "M&A_Investment",
    "Earnings_Contract",
    "Macro_Indicator",
    "Policy_Regulation",
    "Geopolitical_Risk",
    "Management_Risk",
    "General_Market",
    "Non_Economic",  # 주식·경제와 무관한 사회·사건사고·정치·스포츠·연예 등
)

DEFAULT_EVENT_TYPE = "General_Market"

SYSTEM_PROMPT = (
    "당신은 알고리즘 트레이딩을 위한 금융 뉴스 분류 AI입니다. "
    "제공된 뉴스를 분석하여, 매매 엔진이 파싱할 수 있도록 아래 정의된 JSON 형식으로만 응답하십시오.\n\n"
    "[분석 기준]\n"
    "1. Depth 1 (방향성 - Direction)\n"
    "- direction: 이 뉴스가 미치는 전반적인 긍/부정 상태를 정수로 반환. "
    "(1: 호재, 0: 중립/단순시황, -1: 악재)\n\n"
    "2. Depth 2 (영향 범위 및 타겟 - Impact Scope & Target)\n"
    "- target_sector: 뉴스가 다루는 핵심 산업군 명칭 (예: 반도체, 2차전지, 금융 등. 특정 섹터가 없으면 null)\n"
    "- is_sector_impact: 위 target_sector 산업군 내부에 유의미한 영향을 미치는가? (true/false)\n"
    "- is_domestic_impact: 한국 코스피/코스닥 지수 및 국내 거시경제 전반에 영향을 미치는가? (true/false)\n"
    "- is_overseas_impact: 글로벌 매크로 및 지정학적 정세에 영향을 미치는가? (true/false)\n"
    "(주의: 하나의 뉴스가 여러 곳에 영향을 미칠 수 있으므로 복수 true 가능)\n\n"
    "3. Depth 3 (메타데이터 및 이벤트 - Metadata & Event)\n"
    "- themes: 본문에서 가장 강조된 핵심 기술/테마 키워드 (최대 2개. 예: [\"HBM\", \"전고체\"])\n"
    "- event_type: 뉴스의 핵심 이벤트 성격을 아래 Enum 중 하나로만 반환.\n"
    "  * \"M&A_Investment\": 인수합병, 대규모 투자, 설비 증설\n"
    "  * \"Earnings_Contract\": 어닝 서프라이즈/쇼크, 대규모 수주 계약\n"
    "  * \"Macro_Indicator\": 금리 결정, 환율 변동, CPI/고용 등 거시 경제 지표 발표\n"
    "  * \"Policy_Regulation\": 정부 정책, 규제 완화/강화, 법안 통과\n"
    "  * \"Geopolitical_Risk\": 전쟁, 관세, 무역 분쟁, 수출 통제\n"
    "  * \"Management_Risk\": (기업의) 횡령, 배임, 경영권 분쟁, 상장폐지 우려 (돌발 악재). "
    "기업 이슈가 아닌 일반 범죄·사건사고·정치 뉴스에는 절대 쓰지 마세요.\n"
    "  * \"General_Market\": 주식·경제와 관련은 있으나 특정 이벤트가 없는 단순 시황, 전문가 전망\n"
    "  * \"Non_Economic\": 주식·경제·산업과 무관한 뉴스(강력범죄, 사건사고, 스포츠, 연예, 일반 사회, "
    "인사·행정, 순수 외교·정치 등 시장 영향이 없는 뉴스)\n\n"
    "[중요 게이트 규칙]\n"
    "특정 상장 종목·산업군·거시경제에 '실질적' 영향이 없는 뉴스는 아래처럼 처리하세요:\n"
    "- event_type = \"Non_Economic\", direction = 0\n"
    "- is_sector_impact/is_domestic_impact/is_overseas_impact 는 모두 false\n"
    "- target_sector = null, themes = []\n"
    "예: 강력범죄·화재·교통사고, 스포츠·연예, 순수 정치 공방·인사, 시장과 무관한 국제 사회 뉴스 등.\n"
    "반대로 금리·환율·정책·수출통제·기업 실적/투자 등 시장에 영향을 주는 뉴스만 해당 event_type을 부여하세요.\n\n"
    "[출력 형식 (Strict JSON)]\n"
    "{\n"
    '  "depth_1": { "direction": 1 },\n'
    '  "depth_2": {\n'
    '    "target_sector": "string",\n'
    '    "is_sector_impact": true,\n'
    '    "is_domestic_impact": false,\n'
    '    "is_overseas_impact": false\n'
    "  },\n"
    '  "depth_3": {\n'
    '    "themes": ["string"],\n'
    '    "event_type": "string"\n'
    "  }\n"
    "}\n\n"
    + sector_prompt_block()
    + "\n\n"
    + theme_prompt_block()
)


def _coerce_direction(value: Any) -> int:
    """방향성을 -1/0/1 정수로 강제한다. 파싱 불가/범위 밖은 0(중립)."""
    try:
        num = int(value)
    except (TypeError, ValueError):
        return 0
    if num > 0:
        return 1
    if num < 0:
        return -1
    return 0


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "t"}
    return bool(value)


def _coerce_sector(value: Any) -> str | None:
    """통제 어휘(sectors.py)의 표준 섹터로 정규화한다. 어휘에 없으면 None."""
    if value is None:
        return None
    return normalize_sector(str(value))


def _coerce_themes(value: Any) -> list[str]:
    """통제 어휘(themes.py)로 정규화한 최대 2개의 정식 테마명 리스트로 변환한다.

    어휘에 없는 잡음 테마(예: '월드컵')는 드롭한다.
    """
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return []
    return normalize_themes([str(x) for x in items], limit=2)


def _coerce_event_type(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return text if text in EVENT_TYPES else DEFAULT_EVENT_TYPE


def normalize_classification(raw: dict) -> dict:
    """AI 원본 응답을 매매 엔진이 신뢰할 수 있는 고정 스키마로 정규화한다."""
    raw = raw or {}
    depth_1 = raw.get("depth_1") or {}
    depth_2 = raw.get("depth_2") or {}
    depth_3 = raw.get("depth_3") or {}
    result = {
        "depth_1": {"direction": _coerce_direction(depth_1.get("direction"))},
        "depth_2": {
            "target_sector": _coerce_sector(depth_2.get("target_sector")),
            "is_sector_impact": _coerce_bool(depth_2.get("is_sector_impact")),
            "is_domestic_impact": _coerce_bool(depth_2.get("is_domestic_impact")),
            "is_overseas_impact": _coerce_bool(depth_2.get("is_overseas_impact")),
        },
        "depth_3": {
            "themes": _coerce_themes(depth_3.get("themes")),
            "event_type": _coerce_event_type(depth_3.get("event_type")),
        },
    }
    # 게이트 재확정: 경제 무관(Non_Economic)이면 방향/영향/섹터/테마를 모두 비활성화(일관성 보장).
    if result["depth_3"]["event_type"] == "Non_Economic":
        result["depth_1"]["direction"] = 0
        result["depth_2"] = {
            "target_sector": None, "is_sector_impact": False,
            "is_domestic_impact": False, "is_overseas_impact": False,
        }
        result["depth_3"]["themes"] = []
    return result


def classify_news(ai_client: AIClient, text: str) -> dict:
    """AI를 호출해 뉴스를 분류하고 정규화된 결과를 반환한다(캐시 미사용)."""
    raw = ai_client.complete_json(SYSTEM_PROMPT, text, purpose="news_classify")
    return normalize_classification(raw)


def get_or_compute_news_classification(
    cache_repo: AIScoreCacheRepository,
    ai_client: AIClient,
    subject_id: str,
    text: str,
) -> dict:
    """캐시에 있으면 그대로 반환하고, 없으면 AI를 호출해 분류 후 캐시에 저장한다."""
    model = ai_client.model_name
    cached = cache_repo.get(SUBJECT_TYPE, subject_id, PROMPT_VERSION, model)
    if cached is not None:
        return cached.score_json

    result = classify_news(ai_client, text)
    cache_repo.save(
        AIScoreCacheRecord(
            id=str(uuid.uuid4()),
            subject_type=SUBJECT_TYPE,
            subject_id=subject_id,
            prompt_version=PROMPT_VERSION,
            model=model,
            score_json=result,
        )
    )
    return result
