"""OpenAI API 클라이언트 구현체.

키는 백엔드 .env(OPENAI_API_KEY)에서만 읽으며 프론트엔드에는 절대 노출하지 않는다.
모든 호출은 백엔드 라우터(app/api/routers/ai.py 등)를 경유한다.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

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
        response = self._create(messages, temperature, response_format={"type": "json_object"})
        self._record_usage(response, purpose)
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def complete_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Any],
        temperature: float = 0.2,
        purpose: str = "unknown",
        max_rounds: int = 4,
    ) -> dict:
        if self._client is None:
            raise AIUnavailableError("OPENAI_API_KEY가 설정되지 않아 AI 기능을 사용할 수 없습니다.")

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for _ in range(max_rounds):
            response = self._create(messages, temperature, tools=tools, tool_choice="auto")
            self._record_usage(response, purpose)
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                content = message.content or ""
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    break  # 도구 호출 없이 곧장 non-JSON 답을 준 경우 — 마지막 강제 호출로 넘어간다
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = tool_executor(tc.function.name, args)
                except Exception as exc:  # noqa: BLE001 - 도구 실행 실패도 AI에게 알려 계속 진행시킨다
                    result = {"error": str(exc)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # max_rounds를 다 썼거나 non-JSON 응답 — 도구 없이 마지막 1회로 최종 JSON을 강제한다.
        messages.append({"role": "user", "content": "지금까지의 정보로 도구 호출 없이 최종 JSON으로만 답하세요."})
        response = self._create(messages, temperature, response_format={"type": "json_object"})
        self._record_usage(response, purpose)
        content = response.choices[0].message.content or "{}"
        return json.loads(content)

    def _create(self, messages: list[dict], temperature: float, **kwargs: Any):
        payload: dict[str, Any] = {"model": self._model, "temperature": temperature, "messages": messages, **kwargs}
        try:
            return self._client.chat.completions.create(**payload)
        except BadRequestError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            param = body.get("param")
            if param == "temperature":
                # gpt-5 계열 reasoning 모델(gpt-5*, gpt-5.6-sol/terra/luna 등)은 기본값(1)
                # 외의 temperature를 지원하지 않는다. 해당 오류일 때만 temperature 없이 재시도한다.
                payload.pop("temperature")
            elif param == "reasoning_effort":
                # 같은 계열 reasoning 모델은 tools(함수 호출)와 함께 쓸 때 chat.completions
                # 엔드포인트에서 reasoning_effort를 명시적으로 "none"으로 지정해야 한다
                # (미지정 시 계정 기본값이 걸려 400). ai.free_prompt의 도구 호출 모드에서
                # 실제로 이 오류를 만나 회귀 테스트를 추가했다.
                payload["reasoning_effort"] = "none"
            else:
                raise
            return self._client.chat.completions.create(**payload)

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
