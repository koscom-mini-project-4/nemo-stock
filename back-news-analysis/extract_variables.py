"""캐시 우선 조회 -> 미스 건만 AI로 빠르게(동기) 채우는 온디맨드 경로.

백테스트 도중 필요한 뉴스가 build_pool로 미리 만들어 둔 AI 풀(캐시)에 없으면, 이 모듈이
해당 건만 즉시 채점(scoring.score_one)+임베딩(embeddings.embed_one)해서 캐시에 추가한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import embeddings
import scoring
from cache_store import CacheStore
from clustering import assign_one
from schemas import NewsRecord, NewsVariables


def candidate_url_hashes(
    company: str, all_records: list[NewsRecord], as_of: date, lookback_days: int = 14
) -> list[str]:
    """company 문자열이 제목/본문/요약에 등장하는, as_of 기준 최근 lookback_days 이내 뉴스만 후보로 추림.

    92,229건 전체를 매번 AI로 훑는 것을 피하기 위한 무비용 사전 필터(단순 문자열 포함 검사).
    """
    start = as_of - timedelta(days=lookback_days)
    out = []
    for r in all_records:
        pub_date = datetime.strptime(r.published_at.split(" ")[0], "%Y-%m-%d").date()
        if not (start <= pub_date <= as_of):
            continue
        if company in r.title or company in r.summary or company in r.content:
            out.append(r.url_hash)
    return out


def ensure_variables(
    url_hashes: list[str],
    store: CacheStore,
    records_by_hash: dict[str, NewsRecord],
) -> dict[str, NewsVariables]:
    """url_hashes 각각에 대해 캐시를 조회하고, 없으면 AI로 즉시 계산해 캐시에 채운 뒤 반환한다."""
    clusters = store.get_clusters()
    result: dict[str, NewsVariables] = {}
    misses: list[str] = []

    for h in url_hashes:
        cached = store.get_variables(h)
        if cached is not None:
            result[h] = cached
        else:
            misses.append(h)

    if misses:
        print(f"[extract_variables] 캐시 미스 {len(misses)}건 -> AI로 즉시 추출")
    for h in misses:
        record = records_by_hash[h]
        variables = scoring.score_one(record)
        vec = embeddings.embed_one(record)
        cluster_id = assign_one(record, vec, variables.related_tickers, variables.related_industries, clusters)
        variables.cluster_id = cluster_id
        store.set_variables(variables)
        result[h] = variables

    if misses:
        store.save_clusters(clusters)

    return result
