"""클러스터 후보 사전 필터링 — nemo-stock 통합 시 신규 추가(upstream에는 없는 파일).

classifier.call_ai()는 "최근 보관기간(기본 7일) 내 클러스터 후보 전부"를 텍스트로 프롬프트에
넣어 LLM이 "같은 사건이면 그 클러스터에 붙여라"를 판단하게 한다. 문제는 그 후보 수가
보관기간에 비례해서가 아니라 그 기간의 "뉴스 유입량"에 비례한다는 것 — 클러스터가 많아질수록
분류 1건마다 반복해서 들어가는 후보 목록 텍스트가 계속 커져서(실측: 후보 968개일 때 약
9만 자, 4~5만 토큰) 비용/레이턴시가 뉴스량과 함께 무한정 늘어난다.

여기서는 새 기사 제목을 임베딩(text-embedding-3-small)해 기존 클러스터들의 대표제목
임베딩과 코사인 유사도를 계산하고, 상위 CLUSTER_CANDIDATE_TOP_K개만 call_ai()에 넘긴다.
채팅 모델 대비 임베딩 호출은 훨씬 싸고 빨라서(기사 제목 하나당 토큰 수십 개) 이 사전
필터링 자체의 비용은 무시할 만한 수준이다. LLM이 보던 "뉴스 제목 vs 기존 클러스터 대표제목"
비교 범위를 좁힌 것뿐이라, 클러스터 판정 로직(classifier.SYSTEM_PROMPT)은 그대로 둔다.
"""
from __future__ import annotations

import math
from typing import Optional

from openai import OpenAI

from . import classifier
from .config import OPENAI_API_KEY

EMBEDDING_MODEL = "text-embedding-3-small"

_clients: dict[str, OpenAI] = {}


def _client_once(api_key: str = None) -> OpenAI:
    key = api_key or OPENAI_API_KEY
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY 가 없습니다. .env 에 넣거나 NewsTrader(api_key=...) 로 넘기세요.")
    if key not in _clients:
        _clients[key] = OpenAI(api_key=key)
    return _clients[key]


def embed(text: str, api_key: str = None) -> list[float]:
    """텍스트 하나를 임베딩한다. 사용량은 classifier._usage_sink(있으면)에 함께 기록한다
    (관리자 페이지 AI 사용량 통계에 purpose="newsstock_embed"로 잡힘)."""
    client = _client_once(api_key)
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text or "(제목 없음)")
    _report_usage(resp)
    return list(resp.data[0].embedding)


def _report_usage(resp) -> None:
    sink = classifier._usage_sink  # noqa: SLF001 - 모듈 레벨 훅을 그대로 재사용(별도 등록 불필요)
    if sink is None:
        return
    usage = getattr(resp, "usage", None)
    if usage is None:
        return
    try:
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or prompt_tokens
        sink("newsstock_embed", EMBEDDING_MODEL, prompt_tokens, 0, total_tokens)
    except Exception:  # noqa: BLE001 - 사용량 기록 실패가 분류를 막으면 안 된다
        pass


def cosine_similarity(a: Optional[list[float]], b: Optional[list[float]]) -> float:
    if not a or not b:
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return -1.0
    return dot / (norm_a * norm_b)


def top_k_similar(query_embedding: list[float], candidates: list[dict], k: int) -> list[dict]:
    """candidates 각각은 최소 "embedding" 키(list[float] | None)를 가진 dict여야 한다
    (db.recent_clusters 반환 형태). 임베딩이 없는 후보(과거 마이그레이션 이전 데이터 등)는
    유사도 최하위로 취급해 자연스럽게 top-K 밖으로 밀려나되, 후보 자체가 K개 미만이면
    여전히 결과에 포함될 수 있다."""
    if k <= 0 or not candidates:
        return []
    scored = [(cosine_similarity(query_embedding, c.get("embedding")), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:k]]
