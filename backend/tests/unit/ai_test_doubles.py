"""테스트 전용 AIClient 더블. 실제 OpenAI 호출 없이 AI 관련 로직을 검증하기 위해 사용한다."""

from __future__ import annotations

from app.ai.base import AIClient, AIUnavailableError


class FakeAIClient(AIClient):
    def __init__(self, responses: list[dict] | None = None, model: str = "fake-model", available: bool = True):
        self._responses = list(responses or [])
        self._model = model
        self._available = available
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        if not self._available:
            raise AIUnavailableError("fake client unavailable")
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("FakeAIClient: 더 이상 준비된 응답이 없습니다.")
        return self._responses.pop(0)
