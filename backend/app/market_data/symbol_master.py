"""종목코드 -> 한글 종목명 매핑 (정적 캐시).

nemo-stock에는 종목 마스터 API가 없다(scheduler.interval의 universe는 자유 텍스트
콤마 구분 종목코드를 그대로 받는다). 별도 마스터 데이터 API 연동 없이도 "종목번호로
캐싱해서 한국어로 검색/표시"할 수 있도록, nemo-poc(app/market_data/universe.py)의
대표 종목 유니버스를 그대로 재사용해 최소한의 매핑을 제공한다.

매핑에 없는 종목코드는 조회 시 이름 없이(코드만) 반환한다 — 존재하지 않는 코드로
취급하거나 오류를 내지 않는다(임의 종목코드를 자유롭게 쓰는 기존 워크플로 설계와의
호환을 위함).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    name: str


# nemo-poc의 UNIVERSE(대표 종목 8개)와 동일한 목록. 필요 시 여기에 추가하면 된다.
_SYMBOLS: list[SymbolInfo] = [
    SymbolInfo("005930", "삼성전자"),
    SymbolInfo("000660", "SK하이닉스"),
    SymbolInfo("035420", "NAVER"),
    SymbolInfo("035720", "카카오"),
    SymbolInfo("051910", "LG화학"),
    SymbolInfo("005380", "현대차"),
    SymbolInfo("006400", "삼성SDI"),
    SymbolInfo("068270", "셀트리온"),
]

_BY_SYMBOL: dict[str, str] = {s.symbol: s.name for s in _SYMBOLS}


def get_symbol_name(symbol: str) -> str | None:
    """매핑에 있으면 한글 종목명을, 없으면 None을 반환한다."""
    return _BY_SYMBOL.get(symbol)


def list_symbols() -> list[SymbolInfo]:
    return list(_SYMBOLS)


def search_symbols(query: str) -> list[SymbolInfo]:
    """종목코드 또는 한글 종목명 부분 일치 검색(대소문자 무시). 빈 질의면 전체 목록."""
    q = query.strip()
    if not q:
        return list(_SYMBOLS)
    q_lower = q.lower()
    return [s for s in _SYMBOLS if q in s.symbol or q_lower in s.name.lower()]
