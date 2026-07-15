"""OpenDART(금융감독원 전자공시) 공시 목록 수집 클라이언트.

엔드포인트: https://opendart.fss.or.kr/api/list.json
API 키는 opendart.fss.or.kr에서 발급받아 backend/.env의 DART_API_KEY로 설정한다.

PoC 단순화: list.json 응답에 포함된 stock_code로 관심 종목만 클라이언트 측에서 필터링한다
(공시 원문 문서(document.xml, zip)는 이번 PoC 범위에서 제외 — report_nm(공시 제목)을
AI 점수화의 입력 텍스트로 사용한다).

주의(실사용 중 발견된 한계): OpenDART list.json은 corp_code를 지정하지 않으면 시장 전체
공시를 반환한다. 예를 들어 10일 구간에도 총 페이지가 수천 건에 달할 수 있어(2026-07-15
실측: 6,920건/2,307페이지), 특정 종목만 원하더라도 전체를 끝까지 순회하면 응답이 사실상
끝나지 않는다(수십 분 이상, HTTP 타임아웃으로 500 발생). 이를 막기 위해 max_pages로
스캔 범위를 제한한다 — 상한에 도달하면 그 시점까지 찾은 결과만 반환한다(완전성 대신
응답성을 우선하는 보수적 타협). 특정 종목의 corp_code를 사전에 매핑해두면 서버 측에서
정확히 필터링할 수 있으나, corpCode.xml 마스터 동기화가 필요해 이번 PoC 범위 밖으로 남겨둔다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import httpx

DEFAULT_BASE_URL = "https://opendart.fss.or.kr/api/list.json"

# OpenDART status 코드: "000" 정상, "013" 조회된 데이터 없음(오류 아님)
_STATUS_OK = "000"
_STATUS_NO_DATA = "013"


class OpenDartAPIError(RuntimeError):
    pass


@dataclass
class DisclosureItem:
    rcept_no: str
    corp_code: str
    corp_name: str
    stock_code: str | None
    report_nm: str
    rcept_dt: date


class OpenDartClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OpenDartClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_disclosures(
        self,
        start: date,
        end: date,
        stock_codes: list[str] | None = None,
        page_count: int = 100,
        max_pages: int = 20,
    ) -> list[DisclosureItem]:
        """[start, end] 기간의 공시를 조회한다. stock_codes가 주어지면 해당 종목코드만 남긴다.

        max_pages: corp_code 미지정 조회는 시장 전체를 스캔하므로(클래스 docstring 참조)
        무한정 페이지를 넘기지 않도록 상한을 둔다. 상한에 도달하면 그때까지의 결과만 반환한다.
        """
        wanted = set(stock_codes) if stock_codes else None
        items: list[DisclosureItem] = []
        page_no = 1

        while page_no <= max_pages:
            params = {
                "crtfc_key": self._api_key,
                "bgn_de": start.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "page_no": page_no,
                "page_count": page_count,
            }
            response = self._client.get(self._base_url, params=params)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == _STATUS_NO_DATA:
                break
            if status != _STATUS_OK:
                raise OpenDartAPIError(f"OpenDART API 오류: {data.get('message', status)}")

            for row in data.get("list", []) or []:
                stock_code = (row.get("stock_code") or "").strip() or None
                if wanted is not None and stock_code not in wanted:
                    continue
                items.append(
                    DisclosureItem(
                        rcept_no=row["rcept_no"],
                        corp_code=row["corp_code"],
                        corp_name=row["corp_name"],
                        stock_code=stock_code,
                        report_nm=row["report_nm"],
                        rcept_dt=datetime.strptime(row["rcept_dt"], "%Y%m%d").date(),
                    )
                )

            total_page = int(data.get("total_page", 1) or 1)
            if page_no >= total_page:
                break
            page_no += 1

        return items
