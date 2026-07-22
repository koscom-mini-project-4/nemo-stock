"""back-news-analysis 공용 데이터 구조."""

from __future__ import annotations

from dataclasses import dataclass, field

# depth2(긍정/중립/부정) -> 방향값
SENTIMENT_BY_DEPTH2 = {"긍정": 1, "중립": 0, "부정": -1}
# impact_grade(1~9) -> 크기값. 등급 5(보통)를 magnitude 1.0에 맞춰 선형 스케일.
IMPACT_GRADE_MIN = 1
IMPACT_GRADE_MAX = 9


def magnitude_from_grade(grade: int) -> float:
    return grade / 5.0


@dataclass
class NewsRecord:
    url_hash: str
    url: str
    title: str
    content: str
    summary: str
    published_at: str  # "YYYY-MM-DD HH:MM:SS"


@dataclass
class NewsVariables:
    """뉴스 1건에서 AI로 추출한 고정 스키마 10개 필드 + 파생값(strength 등)."""

    url_hash: str
    published_at: str
    depth1: str  # 뉴스의 상위 분류 (예: 증권)
    depth2: str  # 긍정 / 중립 / 부정
    depth3: str  # 세부 이벤트 유형 (예: 실적이익)
    scope_type: str  # 주요 영향 범위: 종목직접 / 업종전반 / 시장전체
    related_tickers: list[str]  # 직접 관련 종목
    related_industries: list[str]  # 관련 업종
    impact_grade: int  # 1(매우 경미) ~ 9(전쟁·내전 등 국가적 충격) — 등급별 예시는 scoring.py 참조
    time_horizon: str  # 단기 / 중기 / 장기
    confidence: str  # 확실 / 보통 / 불확실
    reasoning: str  # 분류 근거
    cluster_id: str | None = None
    model: str = ""
    prompt_version: str = ""

    @property
    def sentiment(self) -> int:
        """depth2(긍정/중립/부정)로부터 파생되는 방향값(+1/0/-1)."""
        return SENTIMENT_BY_DEPTH2.get(self.depth2, 0)

    @property
    def magnitude(self) -> float:
        """impact_grade(1~9)로부터 파생되는 크기값(0.2~1.8, 등급 5=1.0)."""
        return magnitude_from_grade(self.impact_grade)

    @property
    def strength(self) -> float:
        """뉴스의 영향도. sentiment(방향) * magnitude(크기)."""
        return self.sentiment * self.magnitude


@dataclass
class ClusterInfo:
    """이벤트 클러스터. 대표 뉴스 임베딩(centroid)을 기준으로 유사 뉴스를 누적한다."""

    cluster_id: str
    representative_url_hash: str
    representative_title: str
    centroid: list[float]
    member_url_hashes: list[str] = field(default_factory=list)
    related_tickers: list[str] = field(default_factory=list)
    related_industries: list[str] = field(default_factory=list)
    first_published_at: str = ""

    @property
    def source_count(self) -> int:
        return len(self.member_url_hashes)
