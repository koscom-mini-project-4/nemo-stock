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


def _fake_openai_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
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
