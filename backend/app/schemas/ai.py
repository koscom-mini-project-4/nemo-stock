from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateDraftRequest(BaseModel):
    idea: str = Field(min_length=1, description="자연어 투자 아이디어")
    universe: list[str] | None = None


class AIUsageDelta(BaseModel):
    """이 호출 1건에서 새로 쌓인 AI 토큰 사용량(§0-11) — AIUsageRepository.list_since()로
    호출 전/후 델타를 구해 채운다. usage_repo가 없거나 기록 실패 시 응답의 usage 필드
    자체가 None이 될 수 있다(하위호환, 필수 아님)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GenerateDraftResponse(BaseModel):
    name: str
    description: str = ""
    graph: dict[str, Any]
    disclaimer: str
    usage: AIUsageDelta | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class WorkflowChatRequest(BaseModel):
    name: str
    graph: dict[str, Any]
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    last_run: dict[str, Any] | None = None


class WorkflowChatResponse(BaseModel):
    reply: str
    changed: bool
    name: str | None = None
    graph: dict[str, Any] | None = None
    disclaimer: str | None = None
    usage: AIUsageDelta | None = None


class BacktestSelectionIn(BaseModel):
    kind: Literal["point", "range"]
    symbol: str
    date: str | None = None  # kind="point"
    start_date: str | None = None  # kind="range"
    end_date: str | None = None  # kind="range"


class BacktestExplainRequest(BaseModel):
    backtest_id: str
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    selection: BacktestSelectionIn


# 응답 형태는 워크플로 챗봇과 동일(reply/changed/name/graph/disclaimer)해서 프론트가
# ChatPanel.vue와 같은 미리보기/적용 UI를 그대로 재사용할 수 있다.
BacktestExplainResponse = WorkflowChatResponse
