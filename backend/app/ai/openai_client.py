"""OpenAI API 클라이언트 구현체.

키는 백엔드 .env(OPENAI_API_KEY)에서만 읽으며 프론트엔드에는 절대 노출하지 않는다.
모든 호출은 백엔드 라우터(app/api/routers/ai.py 등)를 경유한다.
"""

from __future__ import annotations

import json

from openai import OpenAI

from app.ai.base import AIClient, AIUnavailableError


class OpenAIClient(AIClient):
    def __init__(self, api_key: str | None, model: str) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key) if api_key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        if self._client is None:
            raise AIUnavailableError("OPENAI_API_KEY가 설정되지 않아 AI 기능을 사용할 수 없습니다.")

        response = self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
