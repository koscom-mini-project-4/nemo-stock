"""이벤트 점수 -> 종목별 최종 점수 집계.

공식(사용자 지시):
  strength(종목) = direction(+1/0/-1) * magnitude(grade/5)   -- 그 뉴스가 '그 종목'에 주는 영향도
  decay(d)       = 1 / (d + 1)                                -- d = 이벤트 발생 후 경과일
  count_factor   = 1 + 0.3 * log(source_count)                -- 같은 이벤트를 다룬 뉴스 수
  event_score(종목) = strength(종목) * decay(d) * count_factor
  종목 점수 = 그 종목에 관련된 모든 이벤트의 event_score를 합산 -> 평균 -> 정규화(tanh로 [-1, 1])

중요: strength는 종목마다 다르다. 하나의 뉴스가 A/B/C를 함께 다루더라도 A에는 부정 7등급,
B에는 긍정 5등급, C에는 판단 불가(None)일 수 있으며, None인 종목은 평균의 분모에서 제외한다
(0점으로 넣어 다른 이벤트를 희석시키지 않는다).
"""

from __future__ import annotations

import math
from datetime import date, datetime

from schemas import ClusterInfo, NewsVariables


def decay(days_elapsed: int) -> float:
    d = max(days_elapsed, 0)
    return 1.0 / (d + 1)


def count_factor(source_count: int) -> float:
    n = max(source_count, 1)
    return 1 + 0.3 * math.log(n)


def cluster_strength(
    cluster: ClusterInfo, variables_by_hash: dict[str, NewsVariables], company: str
) -> float | None:
    """클러스터(이벤트)가 company에 주는 대표 영향도: 멤버 뉴스의 종목별 strength 평균.

    그 종목에 대한 판단이 하나도 없으면 None(집계 제외).
    """
    strengths = []
    for h in cluster.member_url_hashes:
        variables = variables_by_hash.get(h)
        if variables is None:
            continue
        s = variables.strength_for(company)
        if s is None:
            continue
        strengths.append(s)
    if not strengths:
        return None
    return sum(strengths) / len(strengths)


def event_score(
    cluster: ClusterInfo, variables_by_hash: dict[str, NewsVariables], as_of: date, company: str
) -> float | None:
    """company 관점의 이벤트 점수. 아직 일어나지 않은 이벤트나 판단 불가 이벤트는 None(집계 제외)."""
    event_date = datetime.strptime(cluster.first_published_at.split(" ")[0], "%Y-%m-%d").date()
    days_elapsed = (as_of - event_date).days
    if days_elapsed < 0:
        return None  # as_of 시점에 아직 알 수 없는 뉴스 — 분모에서도 빼야 미래참조가 없다
    strength = cluster_strength(cluster, variables_by_hash, company)
    if strength is None:
        return None
    return strength * decay(days_elapsed) * count_factor(cluster.source_count)


def stock_score(
    company: str,
    as_of: date,
    clusters: list[ClusterInfo],
    variables_by_hash: dict[str, NewsVariables],
) -> float:
    """종목명(company)과 관련된 모든 이벤트의 점수를 합산 -> 평균 -> tanh 정규화."""
    scores = []
    for cluster in clusters:
        if company not in cluster.related_tickers:
            continue
        score = event_score(cluster, variables_by_hash, as_of, company)
        if score is not None:
            scores.append(score)
    if not scores:
        return 0.0
    return math.tanh(sum(scores) / len(scores))
