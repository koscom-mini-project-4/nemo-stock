"""관리자 페이지 사용량 통계 집계(순수 함수, DAO에 의존하지 않아 단위 테스트가 쉽다).

app/api/routers/admin.py가 AIUsageRepository.list_since()로 가져온 레코드를 여기에 넘겨
목적별/모델별로 묶는다.
"""

from __future__ import annotations

from app.dao.base import AIUsageRecord


def aggregate_usage(records: list[AIUsageRecord]) -> dict:
    prompt_tokens = sum(r.prompt_tokens for r in records)
    completion_tokens = sum(r.completion_tokens for r in records)
    total_tokens = sum(r.total_tokens for r in records)

    by_purpose: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    for r in records:
        p = by_purpose.setdefault(r.purpose, {"purpose": r.purpose, "calls": 0, "total_tokens": 0})
        p["calls"] += 1
        p["total_tokens"] += r.total_tokens

        m = by_model.setdefault(r.model, {"model": r.model, "calls": 0, "total_tokens": 0})
        m["calls"] += 1
        m["total_tokens"] += r.total_tokens

    return {
        "total_calls": len(records),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "by_purpose": sorted(by_purpose.values(), key=lambda x: -x["total_tokens"]),
        "by_model": sorted(by_model.values(), key=lambda x: -x["total_tokens"]),
    }
