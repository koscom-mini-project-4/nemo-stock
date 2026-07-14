from __future__ import annotations

import pytest

from app.broker.dummy import DummyOrderExecutionProvider
from app.config import Settings
from app.dependencies import _build_market_data_provider, _build_order_provider
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
