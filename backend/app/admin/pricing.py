"""AI 모델 비용 추정(관리자 페이지 "사용량 통계"의 예상 비용 계산용).

가격은 2026-07-29 기준 공식 가격표를 하드코딩한 스냅샷이다 — 공급자가 가격을 바꾸면
수동 갱신이 필요하다(자동 조회 안 함). Claude Sonnet 5는 2026-08-31까지 도입가
($2.00/$10.00, 1M 토큰당)가 적용되고 이후 정가($3.00/$15.00)로 복귀하니 그 시점 이후
갱신할 것.

AIUsageRecord(app/dao/base.py)가 캐시 히트 여부를 기록하지 않으므로(prompt_tokens만
있고 cached_tokens 없음) prompt_tokens 전부를 표준(비캐시) 입력 단가로 계산한다 —
실제 캐시 할인이 있었다면 이 추정치는 실제보다 높다(상한 추정치).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float


# $/1M 토큰, 표준(비캐시) 단가. app/config.py의 openai_model/anthropic_model/
# ai_model_strategy로 실제 설정 가능한 모델 중심으로 등재(전체 카탈로그 아님).
_PRICES: dict[str, ModelPrice] = {
    # OpenAI — Standard tier
    "gpt-5.6-sol": ModelPrice(5.00, 30.00),
    "gpt-5.6-terra": ModelPrice(2.50, 15.00),
    "gpt-5.6-luna": ModelPrice(1.00, 6.00),
    "gpt-5.4": ModelPrice(2.50, 15.00),
    "gpt-5.4-mini": ModelPrice(0.75, 4.50),
    "gpt-5.4-nano": ModelPrice(0.20, 1.25),
    "gpt-5.2": ModelPrice(1.75, 14.00),
    "gpt-5.1": ModelPrice(1.25, 10.00),
    "gpt-5": ModelPrice(1.25, 10.00),
    "gpt-5-mini": ModelPrice(0.25, 2.00),
    "gpt-5-nano": ModelPrice(0.05, 0.40),
    "gpt-4o": ModelPrice(2.50, 10.00),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
    "gpt-4.1": ModelPrice(2.00, 8.00),
    "gpt-4.1-mini": ModelPrice(0.40, 1.60),
    "gpt-4.1-nano": ModelPrice(0.10, 0.40),
    # Anthropic — claude-sonnet-5는 2026-08-31까지 도입가
    "claude-fable-5": ModelPrice(10.00, 50.00),
    "claude-opus-5": ModelPrice(5.00, 25.00),
    "claude-sonnet-5": ModelPrice(2.00, 10.00),  # 도입가(~2026-08-31), 이후 3.00/15.00
    "claude-haiku-4-5": ModelPrice(1.00, 5.00),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """가격표에 없는 모델이면 None(호출부에서 "가격 미상"으로 처리, 합계에서 제외)."""
    price = _PRICES.get(model)
    if price is None:
        return None
    return (prompt_tokens / 1_000_000) * price.input_per_mtok + (
        completion_tokens / 1_000_000
    ) * price.output_per_mtok
