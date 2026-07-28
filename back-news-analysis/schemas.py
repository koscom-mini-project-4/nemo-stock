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
class TickerImpact:
    """뉴스 1건이 '특정 종목 하나'에 미치는 영향.

    같은 뉴스라도 종목마다 방향/크기가 다르다(예: 경쟁사 리콜 = 자사에 호재, 해당사에 악재).
    그래서 기사 단위 depth2/impact_grade(= 시장 전체 관점)와 별개로 종목마다 따로 매긴다.

    direction/grade가 None이면 "이름은 등장하지만 영향을 판단할 수 없음/없음"을 뜻하며,
    strength도 None이 되어 집계에서 제외된다(0점으로 희석시키지 않는다).
    """

    ticker: str
    direction: str | None  # 긍정 / 중립 / 부정 / None
    grade: int | None  # 1(극히 경미) ~ 9(극심각) / None
    reason: str = ""

    @property
    def sentiment(self) -> int | None:
        if self.direction is None:
            return None
        return SENTIMENT_BY_DEPTH2.get(self.direction, 0)

    @property
    def magnitude(self) -> float | None:
        if self.grade is None:
            return None
        return magnitude_from_grade(self.grade)

    @property
    def strength(self) -> float | None:
        """이 종목에 대한 영향도. sentiment(방향) * magnitude(크기). 판단 불가면 None."""
        sentiment, magnitude = self.sentiment, self.magnitude
        if sentiment is None or magnitude is None:
            return None
        return sentiment * magnitude


@dataclass
class NewsVariables:
    """뉴스 1건에서 AI로 추출한 고정 스키마 필드 + 파생값(strength 등).

    depth2 / impact_grade는 '시장 전체' 관점의 사건 크기, ticker_impacts는 '종목별' 영향이다.
    """

    url_hash: str
    published_at: str
    depth1: str  # 뉴스의 상위 분류 (예: 증권)
    depth2: str  # 긍정 / 중립 / 부정 — 시장 전체 관점의 방향
    depth3: str  # 세부 이벤트 유형 (예: 실적이익)
    scope_type: str  # 주요 영향 범위: 종목직접 / 업종전반 / 시장전체
    ticker_impacts: list[TickerImpact]  # 종목별 방향/등급 (없으면 빈 리스트)
    related_industries: list[str]  # 관련 업종
    impact_grade: int  # 1(매우 경미) ~ 9(전쟁·내전 등 국가적 충격) — 시장 전체 관점
    time_horizon: str  # 단기 / 중기 / 장기
    confidence: str  # 확실 / 보통 / 불확실
    reasoning: str  # 분류 근거
    cluster_id: str | None = None
    model: str = ""
    prompt_version: str = ""

    @property
    def related_tickers(self) -> list[str]:
        """ticker_impacts에서 종목명만 추출(클러스터링/필터링용 기존 인터페이스 유지)."""
        return [t.ticker for t in self.ticker_impacts]

    @property
    def sentiment(self) -> int:
        """depth2(긍정/중립/부정)로부터 파생되는 시장 전체 방향값(+1/0/-1)."""
        return SENTIMENT_BY_DEPTH2.get(self.depth2, 0)

    @property
    def magnitude(self) -> float:
        """impact_grade(1~9)로부터 파생되는 크기값(0.2~1.8, 등급 5=1.0)."""
        return magnitude_from_grade(self.impact_grade)

    @property
    def strength(self) -> float:
        """시장 전체 관점의 영향도. sentiment(방향) * magnitude(크기)."""
        return self.sentiment * self.magnitude

    def impact_for(self, ticker: str) -> TickerImpact | None:
        for t in self.ticker_impacts:
            if t.ticker == ticker:
                return t
        return None

    def strength_for(self, ticker: str) -> float | None:
        """이 뉴스가 특정 종목에 미치는 영향도. 관련 없거나 판단 불가면 None."""
        impact = self.impact_for(ticker)
        return impact.strength if impact is not None else None


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
