"""Anthropic Claude API 클라이언트 구현체 (`AIClient` 인터페이스 구현).

엔드포인트/필드는 공식 문서(platform.claude.com/docs/en/api/messages)를 직접 대조해
확인했다(추정 아님) — `model`/`max_tokens`/`messages` 필수, `system`은 최상위 문자열
파라미터, 도구는 `{"name","description","input_schema"}` 형태(OpenAI의
`{"type":"function","function":{...}}`와 달라 변환이 필요), 응답은 `content`(TextBlock/
ToolUseBlock 배열) + `usage.input_tokens`/`output_tokens`.

app/ai/openai_client.py와 달리 temperature/reasoning_effort 관련 특이 재시도 로직은
없다 — Claude 표준 API는 그런 제약이 없어 더 단순하다.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Callable

from anthropic import Anthropic

from app.ai.base import AIClient, AIUnavailableError
from app.dao.base import AIUsageRecord, AIUsageRepository

_MAX_TOKENS = 8192
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _tool_to_anthropic(tool: dict) -> dict:
    """OpenAI 함수 스펙({"type":"function","function":{"name","description","parameters"}})을
    Anthropic 도구 스펙({"name","description","input_schema"})으로 변환한다."""
    fn = tool.get("function", tool)
    return {
        "name": fn["name"],
        "description": fn.get("description", ""),
        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
    }


def _strip_code_fence(text: str) -> str:
    return _CODE_FENCE_RE.sub("", text).strip()


def _text_from_content(content: list) -> str:
    return "".join(block.text for block in content if getattr(block, "type", None) == "text")


class ClaudeClient(AIClient):
    def __init__(self, api_key: str | None, model: str, usage_repo: AIUsageRepository | None = None) -> None:
        self._model = model
        self._client = Anthropic(api_key=api_key) if api_key else None
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
            raise AIUnavailableError("ANTHROPIC_API_KEY가 설정되지 않아 AI 기능을 사용할 수 없습니다.")

        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        self._record_usage(response, purpose)
        text = _strip_code_fence(_text_from_content(response.content)) or "{}"
        return json.loads(text)

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
            raise AIUnavailableError("ANTHROPIC_API_KEY가 설정되지 않아 AI 기능을 사용할 수 없습니다.")

        claude_tools = [_tool_to_anthropic(t) for t in tools]
        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        for _ in range(max_rounds):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
                tools=claude_tools,
            )
            self._record_usage(response, purpose)
            tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not tool_use_blocks:
                text = _strip_code_fence(_text_from_content(response.content))
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    break  # 도구 호출 없이 곧장 non-JSON 답을 준 경우 — 마지막 강제 호출로 넘어간다

            messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
            tool_results = []
            for block in tool_use_blocks:
                try:
                    result = tool_executor(block.name, block.input)
                except Exception as exc:  # noqa: BLE001 - 도구 실행 실패도 AI에게 알려 계속 진행시킨다
                    result = {"error": str(exc)}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        # max_rounds를 다 썼거나 non-JSON 응답 — 도구 없이 마지막 1회로 최종 JSON을 강제한다.
        messages.append({"role": "user", "content": "지금까지의 정보로 도구 호출 없이 최종 JSON으로만 답하세요."})
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=temperature,
            system=system_prompt,
            messages=messages,
        )
        self._record_usage(response, purpose)
        text = _strip_code_fence(_text_from_content(response.content)) or "{}"
        return json.loads(text)

    def _record_usage(self, response: object, purpose: str) -> None:
        """관리자 페이지 사용량 통계용 호출 기록. usage_repo가 없거나 기록 실패해도 AI 응답
        자체는 절대 막지 않는다(best-effort). OpenAIClient와 동일한 필드 계약(prompt_tokens/
        completion_tokens/total_tokens)에 input_tokens/output_tokens를 매핑한다."""
        if self._usage_repo is None:
            return
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        try:
            prompt_tokens = getattr(usage, "input_tokens", 0) or 0
            completion_tokens = getattr(usage, "output_tokens", 0) or 0
            self._usage_repo.save(
                AIUsageRecord(
                    id=str(uuid.uuid4()),
                    purpose=purpose,
                    model=self._model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                )
            )
        except Exception:  # noqa: BLE001 - 사용량 기록 실패가 AI 응답을 막으면 안 된다
            pass
