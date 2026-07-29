"""app/admin/metrics.py::aggregate_usage 순수 함수 유닛 테스트."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.admin.metrics import aggregate_usage
from app.dao.base import AIUsageRecord


def _rec(purpose: str, model: str, prompt: int, completion: int, total: int) -> AIUsageRecord:
    return AIUsageRecord(
        id=f"{purpose}-{model}-{prompt}", purpose=purpose, model=model,
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
        created_at=datetime(2026, 7, 28),
    )


def test_aggregate_usage_empty():
    result = aggregate_usage([])
    assert result == {
        "total_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        "total_cost_usd": 0.0, "total_unpriced_tokens": 0,
        "by_purpose": [], "by_model": [],
    }


def test_aggregate_usage_totals_and_breakdowns():
    records = [
        _rec("workflow_draft", "gpt-5.6-luna", 100, 20, 120),
        _rec("workflow_draft", "gpt-5.6-luna", 50, 10, 60),
        _rec("newsstock_classify", "gpt-4o-mini", 200, 30, 230),
    ]

    result = aggregate_usage(records)

    assert result["total_calls"] == 3
    assert result["prompt_tokens"] == 350
    assert result["completion_tokens"] == 60
    assert result["total_tokens"] == 410
    assert result["total_unpriced_tokens"] == 0

    # gpt-5.6-luna: $1.00/$6.00 per 1M -> (150*1.00 + 30*6.00)/1e6
    # gpt-4o-mini: $0.15/$0.60 per 1M -> (200*0.15 + 30*0.60)/1e6
    expected_total_cost = (150 * 1.00 + 30 * 6.00) / 1_000_000 + (200 * 0.15 + 30 * 0.60) / 1_000_000
    assert result["total_cost_usd"] == pytest.approx(expected_total_cost)

    by_purpose = {b["purpose"]: b for b in result["by_purpose"]}
    assert by_purpose["workflow_draft"]["calls"] == 2
    assert by_purpose["workflow_draft"]["total_tokens"] == 180
    assert by_purpose["workflow_draft"]["unpriced_tokens"] == 0
    assert by_purpose["workflow_draft"]["cost_usd"] == pytest.approx((150 * 1.00 + 30 * 6.00) / 1_000_000)
    assert by_purpose["newsstock_classify"]["calls"] == 1
    assert by_purpose["newsstock_classify"]["total_tokens"] == 230

    by_model = {b["model"]: b for b in result["by_model"]}
    assert by_model["gpt-5.6-luna"]["calls"] == 2
    assert by_model["gpt-5.6-luna"]["total_tokens"] == 180
    assert by_model["gpt-5.6-luna"]["cost_usd"] == pytest.approx((150 * 1.00 + 30 * 6.00) / 1_000_000)
    assert by_model["gpt-4o-mini"]["calls"] == 1
    assert by_model["gpt-4o-mini"]["total_tokens"] == 230

    # 큰 토큰 순 정렬(newsstock_classify가 230으로 가장 큼)
    assert result["by_purpose"][0]["purpose"] == "newsstock_classify"


def test_aggregate_usage_unknown_model_is_excluded_from_cost():
    records = [_rec("workflow_draft", "some-future-model-nobody-priced-yet", 1000, 200, 1200)]

    result = aggregate_usage(records)

    assert result["total_cost_usd"] == 0.0
    assert result["total_unpriced_tokens"] == 1200
    assert result["by_model"][0]["cost_usd"] is None
    assert result["by_purpose"][0]["unpriced_tokens"] == 1200
