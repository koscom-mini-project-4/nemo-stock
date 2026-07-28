#!/usr/bin/env python
"""AI 변수 풀 빌더 — naver_economy_news.json에서 뉴스를 뽑아 AI로 변수(감성/영향도/관련종목)와
이벤트 클러스터를 추출해 캐시(JSON/SQLite)에 채워 넣는다.

사용법(backend 가상환경 재사용, 별도 venv 불필요):

  # 1) 소량으로 파이프라인 검증 (동기 호출, 즉시 완료, 비용 조금 발생)
  ../backend/.venv/bin/python build_pool.py --sync --limit 20

  # 2) 최근 N건만 빠르게 채워두고 싶을 때 — Batch API로 제출(비용 50% 절감)
  ../backend/.venv/bin/python build_pool.py --submit --limit 1000

  # 3) 92,229건 전체를 AI로 처리 — Batch API 1건당 최대 5만 건 제한이 있어 청크로 나눠 제출
  ../backend/.venv/bin/python build_pool.py --submit --all

  # 4) 제출한 배치(--limit 방식이든 --all 방식이든)가 끝났는지 확인하고, 끝난 만큼 캐시에 반영
  ../backend/.venv/bin/python build_pool.py --poll
"""

from __future__ import annotations

import argparse
import json
import sys

import embeddings
import scoring
from cache_store import get_store
from clustering import assign_clusters
from config import DATA_DIR, DEFAULT_POOL_SIZE
from news_loader import load_news, load_recent_news
from schemas import NewsVariables

STATE_PATH = DATA_DIR / "build_pool_state.json"
ALL_STATE_PATH = DATA_DIR / "build_pool_all_state.json"

# OpenAI Batch API는 1건당 최대 50,000 요청 또는 200MB(파일 크기) 제한이 있다. 실측 결과
# scoring 배치(본문 최대 1500자 포함)는 건당 약 5.3KB로, 4만 건이면 약 210MB가 되어 200MB
# 제한을 초과한다(실패 확인, 2026-07-22). 여유를 두고 2.5만 건 단위로 자른다(약 132MB).
CHUNK_SIZE = 25_000


def _save_to_stores(variables: list[NewsVariables], clusters, stores: list[str]) -> None:
    for kind in stores:
        store = get_store(kind)
        store.bulk_set_variables(variables)
        store.save_clusters(clusters)
        print(f"[build_pool] {kind} 캐시에 변수 {len(variables)}건, 클러스터 {len(clusters)}건 저장 완료")


def run_sync(limit: int, stores: list[str]) -> None:
    """소규모 동기 실행: 뉴스 하나하나 실시간 호출로 채점+임베딩 후 클러스터링까지 즉시 수행."""
    records = load_recent_news(limit)
    print(f"[build_pool:sync] 뉴스 {len(records)}건 동기 처리 시작")

    variables: list[NewsVariables] = []
    vecs: dict[str, list[float]] = {}
    for i, record in enumerate(records, 1):
        v = scoring.score_one(record)
        vecs[record.url_hash] = embeddings.embed_one(record)
        variables.append(v)
        impacts = ", ".join(f"{t.ticker}:{t.direction or '?'}{t.grade if t.grade is not None else '?'}" for t in v.ticker_impacts)
        print(
            f"  [{i}/{len(records)}] {record.title[:40]}... -> depth1={v.depth1} depth2={v.depth2} "
            f"depth3={v.depth3} scope={v.scope_type} impact_grade={v.impact_grade} tickers=[{impacts}]"
        )

    existing_clusters = get_store(stores[0]).get_clusters()
    tickers_by_hash = {v.url_hash: v.related_tickers for v in variables}
    industries_by_hash = {v.url_hash: v.related_industries for v in variables}
    clusters, assignment = assign_clusters(
        records, vecs, tickers_by_hash, industries_by_hash, existing_clusters=existing_clusters
    )
    for v in variables:
        v.cluster_id = assignment.get(v.url_hash)

    _save_to_stores(variables, clusters, stores)


def run_submit(limit: int) -> None:
    records = load_recent_news(limit)
    print(f"[build_pool:submit] 뉴스 {len(records)}건에 대해 배치 작업 2건 제출")
    embedding_batch_id = embeddings.submit_embedding_batch(records)
    scoring_batch_id = scoring.submit_scoring_batch(records)
    STATE_PATH.write_text(
        json.dumps(
            {"limit": limit, "embedding_batch_id": embedding_batch_id, "scoring_batch_id": scoring_batch_id}
        ),
        encoding="utf-8",
    )
    print(f"[build_pool:submit] embedding_batch_id={embedding_batch_id}")
    print(f"[build_pool:submit] scoring_batch_id={scoring_batch_id}")
    print(f"[build_pool:submit] 상태 저장: {STATE_PATH}")
    print("[build_pool:submit] 완료 확인: python build_pool.py --poll")


def run_poll(stores: list[str], timeout_sec: float) -> None:
    if not STATE_PATH.exists():
        print("[build_pool:poll] --limit 방식으로 제출된 배치가 없습니다.")
        return
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    records = load_recent_news(state["limit"])
    records_by_hash = {r.url_hash: r for r in records}

    print(f"[build_pool:poll] scoring batch({state['scoring_batch_id']}) 확인 중...")
    variables = scoring.poll_scoring_batch(state["scoring_batch_id"], records_by_hash, timeout_sec=timeout_sec)
    print(f"[build_pool:poll] embedding batch({state['embedding_batch_id']}) 확인 중...")
    vecs = embeddings.poll_embedding_batch(state["embedding_batch_id"], timeout_sec=timeout_sec)

    if not variables or not vecs:
        print("[build_pool:poll] 아직 하나 이상의 배치가 완료되지 않았습니다. 잠시 후 다시 --poll 하세요.")
        return

    # 기존에 캐시에 쌓여 있던 클러스터를 이어받아야 여러 번 실행해도(혹은 온디맨드 경로와 함께
    # 써도) 클러스터가 매번 초기화되지 않고 하나의 이벤트 집합으로 누적된다.
    existing_clusters = get_store(stores[0]).get_clusters()
    tickers_by_hash = {v.url_hash: v.related_tickers for v in variables}
    industries_by_hash = {v.url_hash: v.related_industries for v in variables}
    clusters, assignment = assign_clusters(
        records, vecs, tickers_by_hash, industries_by_hash, existing_clusters=existing_clusters
    )
    for v in variables:
        v.cluster_id = assignment.get(v.url_hash)

    _save_to_stores(variables, clusters, stores)
    STATE_PATH.unlink(missing_ok=True)
    print("[build_pool:poll] 완료 — 캐시 반영 및 상태 파일 정리됨")


def run_submit_all() -> None:
    """92,229건 전체를 청크(기본 4만 건)로 나눠 청크마다 임베딩+채점 배치를 제출한다."""
    records = load_news()
    total = len(records)
    chunks = [(i, min(i + CHUNK_SIZE, total)) for i in range(0, total, CHUNK_SIZE)]
    print(f"[build_pool:submit-all] 뉴스 {total}건을 {len(chunks)}개 청크(청크당 최대 {CHUNK_SIZE}건)로 제출")

    chunk_states = []
    for idx, (start, end) in enumerate(chunks):
        chunk_records = records[start:end]
        embedding_batch_id = embeddings.submit_embedding_batch(chunk_records)
        scoring_batch_id = scoring.submit_scoring_batch(chunk_records)
        chunk_states.append(
            {
                "index": idx,
                "start": start,
                "end": end,
                "embedding_batch_id": embedding_batch_id,
                "scoring_batch_id": scoring_batch_id,
                "done": False,
            }
        )
        print(f"  청크 {idx} [{start}:{end}] ({end - start}건) -> embedding={embedding_batch_id} scoring={scoring_batch_id}")

    ALL_STATE_PATH.write_text(json.dumps({"total": total, "chunks": chunk_states}), encoding="utf-8")
    print(f"[build_pool:submit-all] 상태 저장: {ALL_STATE_PATH}")
    print("[build_pool:submit-all] 완료 확인: python build_pool.py --poll --all")


def run_poll_all(stores: list[str], timeout_sec: float) -> None:
    if not ALL_STATE_PATH.exists():
        print("[build_pool:poll-all] --all로 제출된 배치가 없습니다.")
        return
    state = json.loads(ALL_STATE_PATH.read_text(encoding="utf-8"))
    all_records = load_news()

    pending = [c for c in state["chunks"] if not c["done"]]
    if not pending:
        print("[build_pool:poll-all] 모든 청크가 이미 처리 완료됨.")
        return

    for chunk_state in pending:
        idx, start, end = chunk_state["index"], chunk_state["start"], chunk_state["end"]
        chunk_records = all_records[start:end]
        records_by_hash = {r.url_hash: r for r in chunk_records}

        print(f"[build_pool:poll-all] 청크 {idx} [{start}:{end}] scoring batch 확인 중...")
        variables = scoring.poll_scoring_batch(
            chunk_state["scoring_batch_id"], records_by_hash, timeout_sec=timeout_sec
        )
        print(f"[build_pool:poll-all] 청크 {idx} embedding batch 확인 중...")
        vecs = embeddings.poll_embedding_batch(chunk_state["embedding_batch_id"], timeout_sec=timeout_sec)

        if not variables or not vecs:
            print(f"[build_pool:poll-all] 청크 {idx}는 아직 완료되지 않음 — 건너뜀")
            continue

        existing_clusters = get_store(stores[0]).get_clusters()
        tickers_by_hash = {v.url_hash: v.related_tickers for v in variables}
        industries_by_hash = {v.url_hash: v.related_industries for v in variables}
        clusters, assignment = assign_clusters(
            chunk_records, vecs, tickers_by_hash, industries_by_hash, existing_clusters=existing_clusters
        )
        for v in variables:
            v.cluster_id = assignment.get(v.url_hash)

        _save_to_stores(variables, clusters, stores)
        chunk_state["done"] = True
        print(f"[build_pool:poll-all] 청크 {idx} 완료 — 누적 클러스터 {len(clusters)}개")

    ALL_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    remaining = [c for c in state["chunks"] if not c["done"]]
    if remaining:
        print(f"[build_pool:poll-all] 아직 {len(remaining)}개 청크 대기 중 — 잠시 후 다시 --poll --all 하세요.")
    else:
        print("[build_pool:poll-all] 전체 청크 처리 완료.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--sync", action="store_true", help="동기 호출로 즉시 소량 처리(검증용)")
    mode.add_argument("--submit", action="store_true", help="Batch API로 대량 처리 작업 제출")
    mode.add_argument("--poll", action="store_true", help="제출한 배치 완료 여부 확인 및 캐시 반영")
    parser.add_argument("--all", action="store_true", help="--submit/--poll 시 92,229건 전체를 청크 단위로 처리")
    parser.add_argument("--limit", type=int, default=DEFAULT_POOL_SIZE, help=f"--all 미지정 시 처리할 뉴스 건수 (기본 {DEFAULT_POOL_SIZE})")
    parser.add_argument("--store", nargs="+", choices=["json", "sqlite"], default=["json", "sqlite"], help="저장할 캐시 종류")
    parser.add_argument("--timeout", type=float, default=0, help="--poll 시 완료까지 대기할 최대 초(기본 0=즉시 1회 확인)")
    args = parser.parse_args()

    if args.sync:
        run_sync(args.limit, args.store)
    elif args.submit:
        run_submit_all() if args.all else run_submit(args.limit)
    elif args.poll:
        run_poll_all(args.store, args.timeout) if args.all else run_poll(args.store, args.timeout)


if __name__ == "__main__":
    main()
