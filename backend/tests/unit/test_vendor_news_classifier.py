"""app/vendor/news_classifier(koscom-mini-project-4/newsstock-lib)에 nemo-stock 통합 시
추가한 수정(classifier.py::call_ai의 temperature 재시도)에 대한 회귀 테스트.
app/ai/openai_client.py의 test_openai_client.py와 동일한 시나리오다.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from openai import BadRequestError

from app.vendor.news_classifier import classifier


def _temperature_error() -> BadRequestError:
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    return BadRequestError(
        "temperature unsupported",
        response=response,
        body={
            "message": "Unsupported value: 'temperature' does not support 0 with this model.",
            "type": "invalid_request_error",
            "param": "temperature",
            "code": "unsupported_value",
        },
    )


def _fake_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


def test_call_ai_retries_without_temperature_on_unsupported_value(monkeypatch):
    create_mock = MagicMock(side_effect=[_temperature_error(), _fake_response('{"cluster_id": null}')])
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    result = classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert result == {"cluster_id": None}
    assert create_mock.call_count == 2
    assert "temperature" in create_mock.call_args_list[0].kwargs
    assert "temperature" not in create_mock.call_args_list[1].kwargs


def test_call_ai_reraises_unrelated_bad_request_error(monkeypatch):
    response = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.openai.com/v1/x"))
    other_error = BadRequestError(
        "bad model",
        response=response,
        body={"message": "unknown model", "type": "invalid_request_error", "param": "model", "code": "invalid"},
    )
    create_mock = MagicMock(side_effect=other_error)
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classifier, "_client_once", lambda api_key=None: fake_client)

    with pytest.raises(BadRequestError):
        classifier.call_ai({"title": "t", "content": "c"}, [], model="gpt-5.6-luna", api_key="sk-test")

    assert create_mock.call_count == 1
