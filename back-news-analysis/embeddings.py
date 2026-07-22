"""임베딩 생성 (클러스터링용). 대량 처리는 OpenAI Batch API(50% 할인), 캐시미스 1건은 동기 호출.

클러스터링을 "새 뉴스마다 기존 대표뉴스 전체를 LLM에 넣어 판단"하는 방식은 뉴스 건수만큼
순차적으로 서로 의존하는 호출이 필요해 Batch API(독립적 요청 묶음)와 근본적으로 맞지 않는다.
대신 뉴스 임베딩 간 코사인 유사도로 "기존 대표뉴스와 얼마나 비슷한가"를 판단하는 방식을 쓴다.
임베딩 자체는 뉴스 1건당 완전히 독립적인 요청이라 Batch API로 한 번에 처리 가능(비용 절감).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from openai import OpenAI

from config import DATA_DIR, EMBEDDING_MODEL, OPENAI_API_KEY
from schemas import NewsRecord

BATCH_INPUT_PATH = DATA_DIR / "embedding_batch_input.jsonl"
BATCH_STATE_PATH = DATA_DIR / "embedding_batch_state.json"


def _client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다 (backend/.env 확인).")
    return OpenAI(api_key=OPENAI_API_KEY)


def _embedding_input_text(record: NewsRecord) -> str:
    # 임베딩은 토큰당 과금이므로 본문 전체 대신 제목+요약만 사용(클러스터링엔 이 정도로 충분).
    return f"{record.title}\n{record.summary}"[:2000]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_one(record: NewsRecord) -> list[float]:
    """캐시 미스 1건에 대한 동기(실시간) 임베딩 호출."""
    client = _client()
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=_embedding_input_text(record))
    return resp.data[0].embedding


def submit_embedding_batch(records: list[NewsRecord]) -> str:
    """records 전체를 하나의 Batch job으로 제출하고 batch_id를 반환한다."""
    client = _client()
    with open(BATCH_INPUT_PATH, "w", encoding="utf-8") as f:
        for r in records:
            line = {
                "custom_id": r.url_hash,
                "method": "POST",
                "url": "/v1/embeddings",
                "body": {"model": EMBEDDING_MODEL, "input": _embedding_input_text(r)},
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    uploaded = client.files.create(file=open(BATCH_INPUT_PATH, "rb"), purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/embeddings",
        completion_window="24h",
        metadata={"purpose": "news-clustering-embeddings"},
    )
    BATCH_STATE_PATH.write_text(json.dumps({"batch_id": batch.id}), encoding="utf-8")
    return batch.id


def poll_embedding_batch(batch_id: str, timeout_sec: float = 0, interval_sec: float = 15) -> dict[str, list[float]]:
    """batch_id 완료를 기다려(timeout_sec<=0이면 즉시 1회 조회만) url_hash->embedding 매핑을 반환.

    완료 전이면 {} 를 반환한다(호출부에서 상태를 보고 재시도).
    """
    client = _client()
    waited = 0.0
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status == "completed":
            break
        if batch.status in ("failed", "expired", "cancelled"):
            raise RuntimeError(f"embedding batch {batch_id} ended with status={batch.status}")
        if timeout_sec <= 0 or waited >= timeout_sec:
            print(f"[embeddings] batch {batch_id} status={batch.status}, 아직 완료되지 않음")
            return {}
        time.sleep(interval_sec)
        waited += interval_sec

    output_file = client.files.content(batch.output_file_id)
    result: dict[str, list[float]] = {}
    for line in output_file.text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        custom_id = row["custom_id"]
        body = row["response"]["body"]
        result[custom_id] = body["data"][0]["embedding"]
    return result
