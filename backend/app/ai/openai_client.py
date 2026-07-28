"""OpenAI API 클라이언트 구현체.

키는 백엔드 .env(OPENAI_API_KEY)에서만 읽으며 프론트엔드에는 절대 노출하지 않는다.
모든 호출은 백엔드 라우터(app/api/routers/ai.py 등)를 경유한다.
"""

from __future__ import annotations

import json
import uuid

from openai import BadRequestError, OpenAI

from app.ai.base import AIClient, AIUnavailableError
from app.dao.base import AIUsageRecord, AIUsageRepository


class OpenAIClient(AIClient):
    def __init__(self, api_key: str | None, model: str, usage_repo: AIUsageRepository | None = None) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key) if api_key else None
        self._usage_repo = usage_repo

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2, purpose: str = "unknown"
    ) -> dict:
        if self._client is None:
            raise AIUnavailableError("OPENAI_API_KEY가 설정되지 않아 AI 기능을 사용할 수 없습니다.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except BadRequestError as exc:
            # gpt-5 계열 reasoning 모델(gpt-5*, gpt-5.6-sol/terra/luna 등)은 기본값(1)
            # 외의 temperature를 지원하지 않는다. 해당 오류일 때만 temperature 없이 재시도한다.
            body = exc.body if isinstance(exc.body, dict) else {}
            if body.get("param") != "temperature":
                raise
            response = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=messages,
            )
        self._record_usage(response, purpose)
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _record_usage(self, response: object, purpose: str) -> None:
        """관리자 페이지 사용량 통계용 호출 기록. usage_repo가 없거나 기록 실패해도 AI 응답
        자체는 절대 막지 않는다(best-effort)."""
        if self._usage_repo is None:
            return
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        try:
            self._usage_repo.save(
                AIUsageRecord(
                    id=str(uuid.uuid4()),
                    purpose=purpose,
                    model=self._model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                )
            )
        except Exception:  # noqa: BLE001 - 사용량 기록 실패가 AI 응답을 막으면 안 된다
            pass
