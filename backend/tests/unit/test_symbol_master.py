"""app.market_data.symbol_master 유닛 테스트(§0-10) — 캐시 교체(load_cache)와 조회 함수 검증.

모듈 레벨 캐시(전역 상태)를 건드리므로, 매 테스트 후 원래 상태로 복원해 다른 테스트
파일(예: ai.news_signal/ai.free_prompt의 8개 폴백 종목 자동 매핑 테스트)에 영향을
주지 않도록 한다.
"""

from __future__ import annotations

import pytest

from app.market_data import symbol_master
from app.market_data.symbol_master import SymbolInfo


@pytest.fixture(autouse=True)
def _restore_cache():
    original = symbol_master.list_symbols()
    yield
    symbol_master.load_cache(original)


def test_fallback_seed_has_eight_symbols_including_samsung():
    names = {s.symbol: s.name for s in symbol_master.list_symbols()}
    assert names.get("005930") == "삼성전자"
    assert symbol_master.cache_size() == 8


def test_get_symbol_name_returns_none_for_unmapped_symbol():
    assert symbol_master.get_symbol_name("000270") is None  # 기아 - 폴백 시드엔 없음


def test_load_cache_replaces_mapping():
    symbol_master.load_cache([SymbolInfo("000270", "기아", "KOSPI")])
    assert symbol_master.cache_size() == 1
    assert symbol_master.get_symbol_name("000270") == "기아"
    assert symbol_master.get_symbol_name("005930") is None  # 삼성전자는 교체돼 사라짐


def test_load_cache_with_empty_list_keeps_existing_cache():
    """동기화 결과가 우연히 비어있어도 기존 매핑을 실수로 날리면 안 된다."""
    symbol_master.load_cache([])
    assert symbol_master.cache_size() == 8
    assert symbol_master.get_symbol_name("005930") == "삼성전자"


def test_search_symbols_matches_code_or_name_case_insensitive():
    symbol_master.load_cache([SymbolInfo("000270", "기아", "KOSPI"), SymbolInfo("066570", "LG전자", "KOSPI")])
    assert [s.symbol for s in symbol_master.search_symbols("기아")] == ["000270"]
    assert [s.symbol for s in symbol_master.search_symbols("lg")] == ["066570"]
    assert [s.symbol for s in symbol_master.search_symbols("0665")] == ["066570"]


def test_search_symbols_empty_query_returns_all():
    symbol_master.load_cache([SymbolInfo("000270", "기아")])
    assert len(symbol_master.search_symbols("")) == 1
