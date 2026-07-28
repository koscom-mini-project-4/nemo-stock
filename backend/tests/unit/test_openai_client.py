"""OpenAIClient 유닛 테스트.

gpt-5 계열 reasoning 모델(gpt-5.6-luna 등)은 기본값(1) 외의 temperature를 거부한다.
실제로 이 오류를 만나 500이 발생했던 회귀를 방지하기 위한 테스트.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

from app.ai.openai_client import OpenAIClient
from app.dao.base import AIUsageRecord, AIUsageRepository


class _FakeUsageRepo(AIUsageRepository):
    def __init__(self):
        self.saved: list[AIUsageRecord] = []

    def save(self, record: AIUsageRecord) -> None:
        self.saved.append(record)

    def list_since(self, since):
        return list(self.saved)


def _temperature_error() -> BadRequestError:
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return BadRequestError(
        "temperature unsupported",
        response=response,
        body={
            "message": "Unsupported value: 'temperature' does not support 0.2 with this model.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )


def _fake_openai_response(content: str, usage: MagicMock | None = None) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = usage
    return resp


def _fake_usage(prompt: int, completion: int, total: int) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt
    u.completion_tokens = completion
    u.total_tokens = total
    return u


def _fake_tool_call(call_id: str, name: str, arguments: str) -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function = MagicMock(name=name, arguments=arguments)
    tc.function.name = name  # MagicMock(name=...)는 .name을 mock 이름으로 안 잡아줘서 명시 설정
    return tc


def _fake_tool_round_response(tool_calls: list, content: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content, tool_calls=tool_calls))]
    resp.usage = None
    return resp


def test_complete_json_retries_without_temperature_on_unsupported_value():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    create_mock = MagicMock(side_effect=[_temperature_error(), _fake_openai_response('{"ok": true}')])
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]

    result = client.complete_json("system", "user")

    assert result == {"ok": True}
    assert create_mock.call_count == 2
    assert "temperature" in create_mock.call_args_list[0].kwargs
    assert "temperature" not in create_mock.call_args_list[1].kwargs


def test_complete_json_reraises_unrelated_bad_request_error():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    other_error = BadRequestError(
        "bad model",
        response=response,
        body={"message": "unknown model", "type": "invalid_request_error", "param": "model", "code": "invalid"},
    )
    create_mock = MagicMock(side_effect=other_error)
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]

    with pytest.raises(BadRequestError):
        client.complete_json("system", "user")

    assert create_mock.call_count == 1


def test_complete_json_records_usage_when_repo_given():
    repo = _FakeUsageRepo()
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna", usage_repo=repo)
    create_mock = MagicMock(
        return_value=_fake_openai_response('{"ok": true}', usage=_fake_usage(100, 20, 120))
    )
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]

    client.complete_json("system", "user", purpose="workflow_draft")

    assert len(repo.saved) == 1
    record = repo.saved[0]
    assert record.purpose == "workflow_draft"
    assert record.model == "gpt-5.6-luna"
    assert (record.prompt_tokens, record.completion_tokens, record.total_tokens) == (100, 20, 120)


def test_complete_json_defaults_purpose_to_unknown():
    repo = _FakeUsageRepo()
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna", usage_repo=repo)
    client._client.chat.completions.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_openai_response('{"ok": true}', usage=_fake_usage(1, 1, 2))
    )

    client.complete_json("system", "user")

    assert repo.saved[0].purpose == "unknown"


def test_complete_json_without_usage_repo_does_not_error():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    client._client.chat.completions.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_openai_response('{"ok": true}', usage=_fake_usage(1, 1, 2))
    )

    result = client.complete_json("system", "user")

    assert result == {"ok": True}


def test_complete_with_tools_executes_tool_call_then_returns_final_json():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    tool_call = _fake_tool_call("call_1", "get_price", '{"symbol": "005930"}')
    create_mock = MagicMock(
        side_effect=[
            _fake_tool_round_response([tool_call]),
            _fake_tool_round_response([], content='{"pass": true, "reason": "ok"}'),
        ]
    )
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]
    executor_calls: list[tuple[str, dict]] = []

    def executor(name: str, args: dict):
        executor_calls.append((name, args))
        return {"price": 71000}

    result = client.complete_with_tools("system", "user", tools=[{"type": "function"}], tool_executor=executor)

    assert result == {"pass": True, "reason": "ok"}
    assert executor_calls == [("get_price", {"symbol": "005930"})]
    assert create_mock.call_count == 2
    # 도구 결과가 대화에 tool 메시지로 이어붙여졌는지 확인
    second_call_messages = create_mock.call_args_list[1].kwargs["messages"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in second_call_messages)


def test_complete_with_tools_forces_final_json_after_max_rounds():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    always_calls_tool = _fake_tool_round_response([_fake_tool_call("call_x", "get_price", "{}")])
    forced_final = _fake_openai_response('{"pass": false}')
    create_mock = MagicMock(side_effect=[always_calls_tool, always_calls_tool, forced_final])
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]

    result = client.complete_with_tools(
        "system", "user", tools=[{"type": "function"}], tool_executor=lambda n, a: {}, max_rounds=2
    )

    assert result == {"pass": False}
    assert create_mock.call_count == 3  # 2회 도구 라운드 + 강제 최종 1회
    assert "tools" not in create_mock.call_args_list[2].kwargs


def test_complete_with_tools_retries_without_temperature_on_unsupported_value():
    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna")
    create_mock = MagicMock(
        side_effect=[_temperature_error(), _fake_tool_round_response([], content='{"pass": true}')]
    )
    client._client.chat.completions.create = create_mock  # type: ignore[union-attr]

    result = client.complete_with_tools("system", "user", tools=[], tool_executor=lambda n, a: {})

    assert result == {"pass": True}
    assert "temperature" not in create_mock.call_args_list[1].kwargs


def test_usage_save_failure_does_not_break_ai_response():
    class _BrokenUsageRepo(AIUsageRepository):
        def save(self, record):
            raise RuntimeError("db down")

        def list_since(self, since):
            return []

    client = OpenAIClient(api_key="sk-test", model="gpt-5.6-luna", usage_repo=_BrokenUsageRepo())
    client._client.chat.completions.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_openai_response('{"ok": true}', usage=_fake_usage(1, 1, 2))
    )

    result = client.complete_json("system", "user")

    assert result == {"ok": True}
