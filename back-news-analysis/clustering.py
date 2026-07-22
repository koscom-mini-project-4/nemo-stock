"""이벤트 클러스터링.

시간순으로 뉴스를 하나씩 훑으며, 임베딩이 기존 클러스터 대표(centroid)와 임계값 이상
유사하면 그 클러스터에 편입하고, 아니면 새 클러스터(자기 자신이 대표)를 만든다.
("대표 뉴스를 정해서 새 뉴스가 들어올 때마다 기존 대표들과 비교해 판단, 없으면 새로 생성"
 이라는 사용자 지시를 임베딩 유사도 기반으로 구현 — 근거는 embeddings.py 모듈 docstring 참조)
"""

from __future__ import annotations

from config import CLUSTER_SIMILARITY_THRESHOLD
from embeddings import cosine_similarity
from schemas import ClusterInfo, NewsRecord


def _next_cluster_id(clusters: list[ClusterInfo]) -> str:
    max_seq = 0
    for c in clusters:
        try:
            max_seq = max(max_seq, int(c.cluster_id.removeprefix("evt_")))
        except ValueError:
            continue
    return f"evt_{max_seq + 1:05d}"


def _merge_unique(target: list[str], additions: list[str]) -> None:
    for item in additions:
        if item not in target:
            target.append(item)


def assign_clusters(
    records: list[NewsRecord],
    embeddings: dict[str, list[float]],
    tickers_by_hash: dict[str, list[str]],
    industries_by_hash: dict[str, list[str]],
    existing_clusters: list[ClusterInfo] | None = None,
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> tuple[list[ClusterInfo], dict[str, str]]:
    """records를 published_at 순으로 순회하며 클러스터에 배정한다.

    반환: (갱신된 클러스터 목록, url_hash -> cluster_id 매핑)
    """
    clusters: list[ClusterInfo] = list(existing_clusters or [])
    assignment: dict[str, str] = {}

    for record in sorted(records, key=lambda r: r.published_at):
        vec = embeddings.get(record.url_hash)
        if vec is None:
            continue  # 임베딩 없는 항목은 이후 on-demand 경로에서 처리

        best_cluster: ClusterInfo | None = None
        best_sim = -1.0
        for cluster in clusters:
            sim = cosine_similarity(vec, cluster.centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster

        tickers = tickers_by_hash.get(record.url_hash, [])
        industries = industries_by_hash.get(record.url_hash, [])

        if best_cluster is not None and best_sim >= threshold:
            best_cluster.member_url_hashes.append(record.url_hash)
            _merge_unique(best_cluster.related_tickers, tickers)
            _merge_unique(best_cluster.related_industries, industries)
            assignment[record.url_hash] = best_cluster.cluster_id
        else:
            new_cluster = ClusterInfo(
                cluster_id=_next_cluster_id(clusters),
                representative_url_hash=record.url_hash,
                representative_title=record.title,
                centroid=vec,
                member_url_hashes=[record.url_hash],
                related_tickers=list(tickers),
                related_industries=list(industries),
                first_published_at=record.published_at,
            )
            clusters.append(new_cluster)
            assignment[record.url_hash] = new_cluster.cluster_id

    return clusters, assignment


def assign_one(
    record: NewsRecord,
    vec: list[float],
    tickers: list[str],
    industries: list[str],
    clusters: list[ClusterInfo],
    threshold: float = CLUSTER_SIMILARITY_THRESHOLD,
) -> str:
    """on-demand 경로: 뉴스 1건을 기존 클러스터 목록에 배정(변경은 clusters를 in-place로 반영)."""
    best_cluster: ClusterInfo | None = None
    best_sim = -1.0
    for cluster in clusters:
        sim = cosine_similarity(vec, cluster.centroid)
        if sim > best_sim:
            best_sim = sim
            best_cluster = cluster

    if best_cluster is not None and best_sim >= threshold:
        best_cluster.member_url_hashes.append(record.url_hash)
        _merge_unique(best_cluster.related_tickers, tickers)
        _merge_unique(best_cluster.related_industries, industries)
        return best_cluster.cluster_id

    new_cluster = ClusterInfo(
        cluster_id=_next_cluster_id(clusters),
        representative_url_hash=record.url_hash,
        representative_title=record.title,
        centroid=vec,
        member_url_hashes=[record.url_hash],
        related_tickers=list(tickers),
        related_industries=list(industries),
        first_published_at=record.published_at,
    )
    clusters.append(new_cluster)
    return new_cluster.cluster_id
