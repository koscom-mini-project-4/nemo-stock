from __future__ import annotations

import pytest

from app.broker.dummy import DummyOrderExecutionProvider
from app.config import Settings
from app.dependencies import _build_ai_client, _build_market_data_provider, _build_order_provider
from app.market_data.dummy import DummyMarketDataProvider


def test_default_settings_select_dummy_providers():
    settings = Settings(_env_file=None)
    assert isinstance(_build_market_data_provider(settings), DummyMarketDataProvider)
    assert isinstance(_build_order_provider(settings), DummyOrderExecutionProvider)


def test_toss_market_data_without_credentials_raises():
    settings = Settings(_env_file=None, market_data_provider="toss")
    with pytest.raises(RuntimeError):
        _build_market_data_provider(settings)


def test_toss_order_provider_without_account_id_raises():
    settings = Settings(
        _env_file=None, order_provider="toss", toss_client_id="id", toss_client_secret="secret"
    )
    with pytest.raises(RuntimeError):
        _build_order_provider(settings)


def test_toss_order_provider_with_full_credentials_builds():
    settings = Settings(
        _env_file=None,
        order_provider="toss",
        toss_client_id="id",
        toss_client_secret="secret",
        toss_account_id="acc-1",
    )
    provider = _build_order_provider(settings)
    assert provider.__class__.__name__ == "TossInvestOrderExecutionProvider"


def test_koscom_market_data_without_credentials_raises():
    settings = Settings(_env_file=None, market_data_provider="koscom")
    with pytest.raises(RuntimeError):
        _build_market_data_provider(settings)


def test_koscom_market_data_with_credentials_builds():
    settings = Settings(
        _env_file=None,
        market_data_provider="koscom",
        koscom_cust_id="NS00000001",
        koscom_auth_key="authkey123",
    )
    provider = _build_market_data_provider(settings)
    assert provider.__class__.__name__ == "KoscomMarketDataProvider"


def test_kis_market_data_without_credentials_raises():
    settings = Settings(_env_file=None, market_data_provider="kis")
    with pytest.raises(RuntimeError):
        _build_market_data_provider(settings)


def test_kis_market_data_with_credentials_builds():
    settings = Settings(
        _env_file=None,
        market_data_provider="kis",
        kis_app_key="key",
        kis_app_secret="secret",
    )
    provider = _build_market_data_provider(settings)
    assert provider.__class__.__name__ == "KISMarketDataProvider"


def test_kis_order_provider_without_account_no_raises():
    settings = Settings(_env_file=None, order_provider="kis", kis_app_key="key", kis_app_secret="secret")
    with pytest.raises(RuntimeError):
        _build_order_provider(settings)


def test_kis_order_provider_with_full_credentials_builds():
    settings = Settings(
        _env_file=None,
        order_provider="kis",
        kis_app_key="key",
        kis_app_secret="secret",
        kis_account_no="12345678-01",
    )
    provider = _build_order_provider(settings)
    assert provider.__class__.__name__ == "KISOrderExecutionProvider"


def test_ai_client_defaults_to_openai():
    settings = Settings(_env_file=None)
    client = _build_ai_client(settings, ai_usage_repo=None)
    assert client.__class__.__name__ == "OpenAIClient"


def test_ai_client_selects_claude_when_configured():
    settings = Settings(_env_file=None, ai_provider="claude", anthropic_api_key="sk-ant-test")
    client = _build_ai_client(settings, ai_usage_repo=None)
    assert client.__class__.__name__ == "ClaudeClient"


def test_ai_client_claude_without_key_is_unavailable():
    """RuntimeError로 막지 않고(기존 OpenAIClient와 동일 동작) available=False로 생성만 되며,
    실제 호출 시점에 각 라우터가 AIUnavailableError를 잡아 400으로 안내한다."""
    settings = Settings(_env_file=None, ai_provider="claude")
    client = _build_ai_client(settings, ai_usage_repo=None)
    assert client.available is False


def test_ai_client_model_override_used_when_given():
    """§0-19: 전략 생성 전용 모델(AI_MODEL_STRATEGY)이 있으면 기본 모델 대신 그걸 쓴다."""
    settings = Settings(_env_file=None, ai_provider="openai", openai_model="gpt-default")
    strategy_client = _build_ai_client(settings, ai_usage_repo=None, model_override="gpt-strategy")
    assert strategy_client.model_name == "gpt-strategy"


def test_ai_client_without_model_override_falls_back_to_default_model():
    settings = Settings(_env_file=None, ai_provider="openai", openai_model="gpt-default")
    client = _build_ai_client(settings, ai_usage_repo=None, model_override=None)
    assert client.model_name == "gpt-default"
