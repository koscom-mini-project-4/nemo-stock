"""종목코드 -> 한글 종목명 매핑 (캐시 기반, §0-10).

과거에는 8개 대표 종목만 정적으로 하드코딩했었다. 이제는 `POST /data/symbols/sync`
(공공데이터포털 금융위원회_주식시세정보, `app/data_ingestion/public_data_price.py::
PublicDataPriceClient.fetch_market_snapshot`)로 KOSPI/KOSDAQ 전 종목을 가져와
`SymbolMasterRepository`(sqlite, durable)에 저장하고, `load_cache()`로 이 모듈의
in-memory 캐시를 교체한다. `app/dependencies.py::build_container()`가 부팅 시 직전
동기화 결과를 sqlite에서 읽어 자동으로 복원하므로 재시작해도 API를 다시 부를 필요는 없다.

캐시가 비어있을 때(최초 부팅 직후, 한 번도 동기화한 적 없음, DATA_GO_KR_SERVICE_KEY 미설정)
는 예전과 동일한 8개 대표 종목을 폴백 시드로 쓴다 — 완전히 빈 상태로 워크플로 빌더/AI 노드가
아무 종목도 못 찾는 상황을 피하기 위함이다.

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
    market: str | None = None


# 캐시가 비어있을 때(동기화 전)의 폴백 시드 — 예전 정적 매핑과 동일한 8개 대표 종목.
_FALLBACK_SYMBOLS: list[SymbolInfo] = [
    SymbolInfo("005930", "삼성전자"),
    SymbolInfo("000660", "SK하이닉스"),
    SymbolInfo("035420", "NAVER"),
    SymbolInfo("035720", "카카오"),
    SymbolInfo("051910", "LG화학"),
    SymbolInfo("005380", "현대차"),
    SymbolInfo("006400", "삼성SDI"),
    SymbolInfo("068270", "셀트리온"),
]

_cache: list[SymbolInfo] = list(_FALLBACK_SYMBOLS)
_by_symbol: dict[str, SymbolInfo] = {s.symbol: s for s in _cache}


def load_cache(symbols: list[SymbolInfo]) -> None:
    """종목 마스터 캐시를 통째로 교체한다(동기화 직후, 부팅 시 sqlite 복원 양쪽에서 호출).

    빈 리스트를 넘기면 아무것도 하지 않는다(기존 캐시 유지) — 동기화 결과가 우연히
    비어있을 때 이미 채워진 매핑을 실수로 날리는 사고를 막기 위함.
    """
    if not symbols:
        return
    global _cache, _by_symbol
    _cache = list(symbols)
    _by_symbol = {s.symbol: s for s in _cache}


def cache_size() -> int:
    return len(_cache)


def get_symbol_name(symbol: str) -> str | None:
    """캐시에 있으면 한글 종목명을, 없으면 None을 반환한다."""
    info = _by_symbol.get(symbol)
    return info.name if info else None


def list_symbols() -> list[SymbolInfo]:
    return list(_cache)


def search_symbols(query: str) -> list[SymbolInfo]:
    """종목코드 또는 한글 종목명 부분 일치 검색(대소문자 무시). 빈 질의면 전체 목록."""
    q = query.strip()
    if not q:
        return list(_cache)
    q_lower = q.lower()
    return [s for s in _cache if q in s.symbol or q_lower in s.name.lower()]
