"""관리자 전용 사용량 통계 API.

백테스트 실행 건수 + AI 호출 수/토큰 수(목적별/모델별)를 한 번에 보여준다. 이 앱은 단일
관리자 계정 구조라(§0 확정 결정) 별도 권한 분기가 없고, 인증 게이트 자체도 없다(§0-17).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.admin.metrics import aggregate_usage
from app.api.deps import get_container
from app.dependencies import Container

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics")
def get_admin_metrics(container: Container = Depends(get_container)) -> dict:
    usage = aggregate_usage(container.ai_usage_repo.list_since(None))
    return {
        "backtest_count": container.backtest_result_repo.count(),
        "ai_usage": usage,
    }
