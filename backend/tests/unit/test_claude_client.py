"""ClaudeClient 유닛 테스트.

Anthropic Messages API 응답 형태(content 블록 배열 + usage.input_tokens/output_tokens)는
공식 문서(platform.claude.com/docs/en/api/messages)를 직접 대조해 확인했다(추정 아님).
실제 앱키로는 호출 검증을 못했으므로 구조/필드 매핑만 mock으로 검증한다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ai.base import AIUnavailableError
from app.ai.claude_client import ClaudeClient
from app.dao.base import AIUsageRecord, AIUsageRepository


class _FakeUsageRepo(AIUsageRepository):
    def __init__(self):
        self.saved: list[AIUsageRecord] = []

    def save(self, record: AIUsageRecord) -> None:
        self.saved.append(record)

    def list_since(self, since):
        return list(self.saved)


def _text_block(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _tool_use_block(call_id: str, name: str, input_dict: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = call_id
    block.name = name
    block.input = input_dict
    block.model_dump.return_value = {"type": "tool_use", "id": call_id, "name": name, "input": input_dict}
    return block


def _fake_usage(input_tokens: int, output_tokens: int) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def _fake_response(content: list, usage: MagicMock | None = None) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.usage = usage
    return resp


def test_complete_json_requires_api_key():
    client = ClaudeClient(api_key=None, model="claude-sonnet-5")
    with pytest.raises(AIUnavailableError):
        client.complete_json("system", "user")


def test_complete_json_parses_text_block():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    client._client.messages.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_response([_text_block('{"ok": true}')])
    )

    result = client.complete_json("system", "user")

    assert result == {"ok": True}


def test_complete_json_strips_markdown_code_fence():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    client._client.messages.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_response([_text_block('```json\n{"ok": true}\n```')])
    )

    result = client.complete_json("system", "user")

    assert result == {"ok": True}


def test_complete_json_records_usage_when_repo_given():
    repo = _FakeUsageRepo()
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5", usage_repo=repo)
    client._client.messages.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_response([_text_block('{"ok": true}')], usage=_fake_usage(100, 20))
    )

    client.complete_json("system", "user", purpose="workflow_draft")

    assert len(repo.saved) == 1
    record = repo.saved[0]
    assert record.purpose == "workflow_draft"
    assert record.model == "claude-sonnet-5"
    assert (record.prompt_tokens, record.completion_tokens, record.total_tokens) == (100, 20, 120)


def test_usage_save_failure_does_not_break_ai_response():
    class _BrokenUsageRepo(AIUsageRepository):
        def save(self, record):
            raise RuntimeError("db down")

        def list_since(self, since):
            return []

    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5", usage_repo=_BrokenUsageRepo())
    client._client.messages.create = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_response([_text_block('{"ok": true}')], usage=_fake_usage(1, 1))
    )

    result = client.complete_json("system", "user")

    assert result == {"ok": True}


def _fake_stream_context(text_chunks: list[str], final_message: MagicMock) -> MagicMock:
    """client.messages.stream(...)의 반환값(컨텍스트 매니저) 더블. 공식 문서 패턴(with ... as
    stream: for text in stream.text_stream ... ; stream.get_final_message())을 그대로 흉내."""
    stream_obj = MagicMock()
    stream_obj.text_stream = iter(text_chunks)
    stream_obj.get_final_message.return_value = final_message
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=stream_obj)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


def test_complete_json_stream_calls_on_chunk_and_returns_parsed_result():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    final_message = _fake_response([_text_block('{"ok": true}')], usage=_fake_usage(10, 5))
    client._client.messages.stream = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_stream_context(['{"ok"', ': true}'], final_message)
    )
    received: list[str] = []

    result = client.complete_json_stream("system", "user", on_chunk=received.append)

    assert result == {"ok": True}
    assert received == ['{"ok"', ': true}']


def test_complete_json_stream_records_usage_from_final_message():
    repo = _FakeUsageRepo()
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5", usage_repo=repo)
    final_message = _fake_response([_text_block('{"ok": true}')], usage=_fake_usage(10, 5))
    client._client.messages.stream = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_stream_context(['{"ok": true}'], final_message)
    )

    client.complete_json_stream("system", "user", purpose="workflow_draft")

    assert len(repo.saved) == 1
    record = repo.saved[0]
    assert record.purpose == "workflow_draft"
    assert (record.prompt_tokens, record.completion_tokens, record.total_tokens) == (10, 5, 15)


def test_complete_json_stream_works_without_on_chunk():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    final_message = _fake_response([_text_block('{"ok": true}')])
    client._client.messages.stream = MagicMock(  # type: ignore[union-attr]
        return_value=_fake_stream_context(['{"ok": true}'], final_message)
    )

    result = client.complete_json_stream("system", "user")

    assert result == {"ok": True}


def test_complete_json_stream_requires_api_key():
    client = ClaudeClient(api_key=None, model="claude-sonnet-5")
    with pytest.raises(AIUnavailableError):
        client.complete_json_stream("system", "user")


def test_complete_with_tools_requires_api_key():
    client = ClaudeClient(api_key=None, model="claude-sonnet-5")
    with pytest.raises(AIUnavailableError):
        client.complete_with_tools("system", "user", tools=[], tool_executor=lambda n, a: {})


def test_complete_with_tools_executes_tool_call_then_returns_final_json():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    tool_block = _tool_use_block("call_1", "get_price", {"symbol": "005930"})
    create_mock = MagicMock(
        side_effect=[
            _fake_response([tool_block]),
            _fake_response([_text_block('{"pass": true, "reason": "ok"}')]),
        ]
    )
    client._client.messages.create = create_mock  # type: ignore[union-attr]
    executor_calls: list[tuple[str, dict]] = []

    def executor(name: str, args: dict):
        executor_calls.append((name, args))
        return {"price": 71000}

    result = client.complete_with_tools(
        "system", "user", tools=[{"type": "function", "function": {"name": "get_price", "parameters": {}}}],
        tool_executor=executor,
    )

    assert result == {"pass": True, "reason": "ok"}
    assert executor_calls == [("get_price", {"symbol": "005930"})]
    assert create_mock.call_count == 2
    # 도구 결과가 tool_result로 대화에 이어붙여졌는지 확인 + tools가 Anthropic 형식으로 변환됐는지.
    first_call_kwargs = create_mock.call_args_list[0].kwargs
    assert first_call_kwargs["tools"] == [{"name": "get_price", "description": "", "input_schema": {}}]
    second_call_messages = create_mock.call_args_list[1].kwargs["messages"]
    tool_result_msg = second_call_messages[-1]
    assert tool_result_msg["role"] == "user"
    assert tool_result_msg["content"][0]["type"] == "tool_result"
    assert tool_result_msg["content"][0]["tool_use_id"] == "call_1"


def test_complete_with_tools_forces_final_json_after_max_rounds():
    client = ClaudeClient(api_key="sk-ant-test", model="claude-sonnet-5")
    always_calls_tool = _fake_response([_tool_use_block("call_x", "get_price", {})])
    forced_final = _fake_response([_text_block('{"pass": false}')])
    create_mock = MagicMock(side_effect=[always_calls_tool, always_calls_tool, forced_final])
    client._client.messages.create = create_mock  # type: ignore[union-attr]

    result = client.complete_with_tools(
        "system", "user", tools=[{"type": "function", "function": {"name": "get_price", "parameters": {}}}],
        tool_executor=lambda n, a: {}, max_rounds=2,
    )

    assert result == {"pass": False}
    assert create_mock.call_count == 3  # 2회 도구 라운드 + 강제 최종 1회
    assert "tools" not in create_mock.call_args_list[2].kwargs
