"""관리자 페이지 사용량 통계 집계(순수 함수, DAO에 의존하지 않아 단위 테스트가 쉽다).

app/api/routers/admin.py가 AIUsageRepository.list_since()로 가져온 레코드를 여기에 넘겨
목적별/모델별로 묶는다.
"""

from __future__ import annotations

from app.admin.pricing import estimate_cost_usd
from app.dao.base import AIUsageRecord


def aggregate_usage(records: list[AIUsageRecord]) -> dict:
    """목적별/모델별 집계에 추정 비용(cost_usd)을 더한다.

    가격표(app/admin/pricing.py)에 없는 모델의 토큰은 cost_usd 계산에서 빠지고
    unpriced_tokens로 집계된다 — total_cost_usd는 그만큼 실제보다 낮게 잡힌
    "하한 추정치"다(합계가 정확하지 않을 수 있음을 관리자 페이지에서 알 수 있도록).
    """
    prompt_tokens = sum(r.prompt_tokens for r in records)
    completion_tokens = sum(r.completion_tokens for r in records)
    total_tokens = sum(r.total_tokens for r in records)

    by_purpose: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    total_cost_usd = 0.0
    total_unpriced_tokens = 0

    for r in records:
        cost = estimate_cost_usd(r.model, r.prompt_tokens, r.completion_tokens)

        p = by_purpose.setdefault(
            r.purpose,
            {"purpose": r.purpose, "calls": 0, "total_tokens": 0, "cost_usd": 0.0, "unpriced_tokens": 0},
        )
        p["calls"] += 1
        p["total_tokens"] += r.total_tokens

        # by_model은 키가 모델 하나뿐이라 같은 그룹 내 cost는 항상 전부 계산 가능하거나
        # 전부 불가능하다(None) — by_purpose처럼 부분 unpriced가 섞이지 않는다.
        m = by_model.setdefault(
            r.model, {"model": r.model, "calls": 0, "total_tokens": 0, "cost_usd": None if cost is None else 0.0}
        )
        m["calls"] += 1
        m["total_tokens"] += r.total_tokens

        if cost is None:
            p["unpriced_tokens"] += r.total_tokens
            total_unpriced_tokens += r.total_tokens
        else:
            p["cost_usd"] += cost
            m["cost_usd"] += cost
            total_cost_usd += cost

    return {
        "total_calls": len(records),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "total_unpriced_tokens": total_unpriced_tokens,
        "by_purpose": sorted(by_purpose.values(), key=lambda x: -x["total_tokens"]),
        "by_model": sorted(by_model.values(), key=lambda x: -x["total_tokens"]),
    }
