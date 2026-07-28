"""공공데이터포털 금융위원회_주식시세정보 API 클라이언트.

엔드포인트: GetStockSecuritiesInfoService/getStockPriceInfo (종목코드+기간 기준 일별 시세)
서비스키는 data.go.kr에서 발급받아 backend/.env의 DATA_GO_KR_SERVICE_KEY로 설정한다.
데이터는 영업일 기준 일 1회(T+1) 갱신되므로 실시간용이 아니라 백테스트용 일봉 소스로 사용한다.

참고: https://www.data.go.kr/data/15094808/openapi.do

주의(실사용 중 발견된 버그, 2026-07-15): 문서상 종목코드 파라미터는 `srtnCd`(정확일치)이지만
**실제 서버는 이 파라미터를 무시하고 시장 전체 데이터를 반환한다**(10일 구간 조회에도
totalCount가 17,000건 이상 — KOSPI/KOSDAQ 전 종목이 섞여 나옴). 대신 `likeSrtnCd`(부분일치)
파라미터를 사용하면 정상적으로 필터링된다(6자리 고정폭 코드이므로 부분일치라도 사실상
정확일치와 동일하게 동작). 혹시 모를 서버 동작 변경에 대비해 응답에서도 `srtnCd`가 요청한
종목코드와 실제로 일치하는 행만 클라이언트에서 한 번 더 걸러낸다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx

from app.dao.base import PriceBarRecord

DEFAULT_BASE_URL = "http://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"


class PublicDataAPIError(RuntimeError):
    pass


class PublicDataPriceClient:
    def __init__(
        self,
        service_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._service_key = service_key
        self._base_url = base_url
        self._timeout = timeout
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "PublicDataPriceClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_daily_prices(
        self, symbol: str, start: date, end: date, num_of_rows: int = 500, max_pages: int = 50
    ) -> list[PriceBarRecord]:
        """종목코드(6자리) 기준 [start, end] 구간의 일별 시세를 모두 가져온다(페이지네이션 자동 처리).

        max_pages: likeSrtnCd 필터가 서버에서 다시 무시되는 경우(과거 실제 발생) 시장 전체
        데이터를 끝까지 순회하지 않도록 안전장치를 둔다.
        """
        bars: list[PriceBarRecord] = []
        page_no = 1
        while page_no <= max_pages:
            params = {
                "serviceKey": self._service_key,
                "resultType": "json",
                "likeSrtnCd": symbol,  # srtnCd(정확일치)는 서버에서 무시됨 — likeSrtnCd만 실제로 필터링된다
                "beginBasDt": start.strftime("%Y%m%d"),
                "endBasDt": end.strftime("%Y%m%d"),
                "numOfRows": num_of_rows,
                "pageNo": page_no,
            }
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
            body = self._parse_body(response)
            all_rows = self._extract_items(body)
            # 페이지네이션 진행 여부는 서버가 알려주는 전체 결과(all_rows/total_count) 기준으로
            # 판단해야 한다. 필터링된 행(matched_rows)만 보고 "이 페이지엔 없음"으로 조기 종료하면
            # (예: likeSrtnCd가 다시 깨져 시장 전체가 섞여 나오는 경우) 뒤 페이지의 실제 데이터를
            # 놓칠 수 있다.
            matched_rows = [r for r in all_rows if (r.get("srtnCd") or "").strip() == symbol]
            bars.extend(self._to_bar(symbol, row) for row in matched_rows)

            total_count = int(body.get("totalCount", 0) or 0)
            if not all_rows or page_no * num_of_rows >= total_count:
                break
            page_no += 1
        return bars

    def fetch_market_snapshot(
        self, as_of: date, num_of_rows: int = 500, max_pages: int = 10, max_days_back: int = 7
    ) -> tuple[date, list[dict]]:
        """as_of(또는 그 이전 최근 영업일)의 KOSPI/KOSDAQ 전 종목 스냅샷을 가져온다(종목
        마스터 캐시 동기화용, §0-10).

        fetch_daily_prices 상단 docstring에 문서화된 서버 동작 — `likeSrtnCd`(종목코드
        필터)를 주지 않고 호출하면 시장 전체 데이터가 반환됨 — 을 이번엔 "버그"가 아니라
        "전 종목 목록을 한 번에 가져오는 방법"으로 그대로 활용한다. 주말/공휴일 등 그날
        시세가 없으면 최대 max_days_back일 전까지 하루씩 물러나며 재시도한다.

        반환: (실제 데이터가 있었던 날짜, [{"symbol","name","market"}, ...] 종목코드 기준
        중복 제거). 데이터를 못 찾으면 (as_of, [])를 반환한다.
        """
        for days_back in range(max_days_back + 1):
            query_date = as_of - timedelta(days=days_back)
            rows = self._fetch_snapshot_rows(query_date, num_of_rows, max_pages)
            if rows:
                return query_date, self._rows_to_symbol_infos(rows)
        return as_of, []

    def _fetch_snapshot_rows(self, query_date: date, num_of_rows: int, max_pages: int) -> list[dict]:
        date_str = query_date.strftime("%Y%m%d")
        rows: list[dict] = []
        page_no = 1
        while page_no <= max_pages:
            params = {
                "serviceKey": self._service_key,
                "resultType": "json",
                "beginBasDt": date_str,
                "endBasDt": date_str,
                "numOfRows": num_of_rows,
                "pageNo": page_no,
            }
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
            body = self._parse_body(response)
            page_rows = self._extract_items(body)
            rows.extend(page_rows)
            total_count = int(body.get("totalCount", 0) or 0)
            if not page_rows or page_no * num_of_rows >= total_count:
                break
            page_no += 1
        return rows

    @staticmethod
    def _rows_to_symbol_infos(rows: list[dict]) -> list[dict]:
        """srtnCd(코드)/itmsNm(종목명)/mrktCtg(시장구분) 추출, 코드 기준 중복 제거, 필드가
        비어있는 행은 skip(방어적 — 실 서버 필드명이 문서와 다를 가능성 대비)."""
        by_symbol: dict[str, dict] = {}
        for row in rows:
            symbol = str(row.get("srtnCd") or "").strip()
            name = str(row.get("itmsNm") or "").strip()
            if not symbol or not name:
                continue
            market = str(row.get("mrktCtg") or "").strip() or None
            by_symbol[symbol] = {"symbol": symbol, "name": name, "market": market}
        return list(by_symbol.values())

    @staticmethod
    def _parse_body(response: httpx.Response) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise PublicDataAPIError(f"응답을 JSON으로 파싱할 수 없습니다: {response.text[:200]}") from exc

        header = data.get("response", {}).get("header", {})
        result_code = header.get("resultCode")
        if result_code not in (None, "00", "0"):
            raise PublicDataAPIError(f"공공데이터 API 오류: {header.get('resultMsg', result_code)}")
        return data.get("response", {}).get("body", {})

    @staticmethod
    def _extract_items(body: dict) -> list[dict]:
        items = body.get("items")
        if not items:
            return []
        rows = items.get("item", []) if isinstance(items, dict) else items
        if isinstance(rows, dict):
            rows = [rows]
        return rows or []

    @staticmethod
    def _to_bar(symbol: str, row: dict) -> PriceBarRecord:
        return PriceBarRecord(
            symbol=symbol,
            trade_date=datetime.strptime(row["basDt"], "%Y%m%d").date(),
            open=float(row["mkp"]),
            high=float(row["hipr"]),
            low=float(row["lopr"]),
            close=float(row["clpr"]),
            volume=int(row["trqu"]),
            source="data.go.kr",
        )
