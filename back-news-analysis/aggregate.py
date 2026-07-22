"""이벤트 점수 -> 종목별 최종 점수 집계.

공식(사용자 지시):
  strength = sentiment(+1/-1) * magnitude(0.5/1.0/1.5)           -- 뉴스의 영향도
  decay(d) = 1 / (d + 1)                                          -- d = 이벤트 발생 후 경과일
  count_factor = 1 + 0.3 * log(source_count)                     -- 같은 이벤트를 다룬 뉴스 수
  event_score = strength * decay(d) * count_factor
  종목 점수 = 그 종목에 관련된 모든 이벤트의 event_score를 합산 -> 평균 -> 정규화(tanh로 [-1, 1])
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


def cluster_strength(cluster: ClusterInfo, variables_by_hash: dict[str, NewsVariables]) -> float:
    """클러스터(이벤트)의 대표 영향도: 멤버 뉴스 strength의 평균."""
    strengths = [variables_by_hash[h].strength for h in cluster.member_url_hashes if h in variables_by_hash]
    if not strengths:
        return 0.0
    return sum(strengths) / len(strengths)


def event_score(cluster: ClusterInfo, variables_by_hash: dict[str, NewsVariables], as_of: date) -> float:
    event_date = datetime.strptime(cluster.first_published_at.split(" ")[0], "%Y-%m-%d").date()
    days_elapsed = (as_of - event_date).days
    if days_elapsed < 0:
        return 0.0  # 아직 일어나지 않은 이벤트는 반영하지 않음
    strength = cluster_strength(cluster, variables_by_hash)
    return strength * decay(days_elapsed) * count_factor(cluster.source_count)


def stock_score(
    company: str,
    as_of: date,
    clusters: list[ClusterInfo],
    variables_by_hash: dict[str, NewsVariables],
) -> float:
    """종목명(company)과 관련된 모든 이벤트의 점수를 합산 -> 평균 -> tanh 정규화."""
    relevant = [c for c in clusters if company in c.related_tickers]
    if not relevant:
        return 0.0
    scores = [event_score(c, variables_by_hash, as_of) for c in relevant]
    avg = sum(scores) / len(scores)
    return math.tanh(avg)
