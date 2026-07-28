"""app/admin/metrics.py::aggregate_usage 순수 함수 유닛 테스트."""

from __future__ import annotations

from datetime import datetime

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

    by_purpose = {b["purpose"]: b for b in result["by_purpose"]}
    assert by_purpose["workflow_draft"] == {"purpose": "workflow_draft", "calls": 2, "total_tokens": 180}
    assert by_purpose["newsstock_classify"] == {"purpose": "newsstock_classify", "calls": 1, "total_tokens": 230}

    by_model = {b["model"]: b for b in result["by_model"]}
    assert by_model["gpt-5.6-luna"] == {"model": "gpt-5.6-luna", "calls": 2, "total_tokens": 180}
    assert by_model["gpt-4o-mini"] == {"model": "gpt-4o-mini", "calls": 1, "total_tokens": 230}

    # 큰 토큰 순 정렬(newsstock_classify가 230으로 가장 큼)
    assert result["by_purpose"][0]["purpose"] == "newsstock_classify"
