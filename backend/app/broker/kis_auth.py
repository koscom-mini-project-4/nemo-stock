"""한국투자증권(KIS) Open API OAuth2 Client Credentials 토큰 발급/캐싱.

market_data/kis_adapter.py와 broker/kis_adapter.py가 공유한다.

엔드포인트/필드명은 공식 GitHub(github.com/koreainvestment/open-trading-api,
examples_llm/kis_auth.py, examples_llm/domestic_stock/*)의 실제 동작하는 예제 코드를
직접 대조해 확인했다(Toss 스켈레톤처럼 순수 추정치가 아님) — 다만 이 프로젝트에는 아직
실제 발급받은 앱키/시크릿이 없어 실호출 검증은 못했다. 사용자가 .env에 KIS_APP_KEY/
KIS_APP_SECRET을 채워 넣은 뒤 실제 모의투자 계좌로 한 번 더 확인하는 것을 권장한다.
"""

from __future__ import annotations

import time

import httpx

TOKEN_PATH = "/oauth2/tokenP"
HASHKEY_PATH = "/uapi/hashkey"

# 실전투자용 tr_id는 전부 이 접두사 중 하나로 시작한다. 모의투자는 첫 글자만 "V"로 바꾼
# 값을 그대로 쓴다(원본 레포 kis_auth.py::_url_fetch의 실제 치환 규칙). 시세 조회(F로
# 시작하는 tr_id)는 모의/실전 구분 없이 동일한 tr_id를 쓰므로 치환 대상이 아니다.
_REAL_TR_PREFIXES = ("T", "J", "C")


def to_paper_tr_id(tr_id: str, is_paper: bool) -> str:
    if is_paper and tr_id and tr_id[0] in _REAL_TR_PREFIXES:
        return "V" + tr_id[1:]
    return tr_id


class KISAuthError(RuntimeError):
    pass


class KISOAuthTokenProvider:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        base_url: str,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._cached_token: str | None = None
        self._expires_at: float = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "KISOAuthTokenProvider":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_token(self) -> str:
        now = time.monotonic()
        if self._cached_token and now < self._expires_at:
            return self._cached_token

        response = self._client.post(
            f"{self._base_url}{TOKEN_PATH}",
            json={
                "grant_type": "client_credentials",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise KISAuthError(f"토큰 발급 응답에 access_token이 없습니다: {data}")

        expires_in = int(data.get("expires_in", 86400))
        self._cached_token = token
        self._expires_at = now + max(expires_in - 30, 0)  # 30초 여유를 두고 만료 처리
        return token

    def auth_headers(self, tr_id: str, is_paper: bool) -> dict[str, str]:
        """공통 요청 헤더. tr_id는 실전 기준 값을 넘기면 모의투자일 때 자동으로 V로
        치환된다(to_paper_tr_id)."""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_token()}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": to_paper_tr_id(tr_id, is_paper),
            "custtype": "P",
        }

    def hashkey(self, body: dict) -> str:
        """POST /uapi/hashkey — 주문 body 무결성 해시. 원본 레포의 order-cash 예제는 이
        헤더 부착을 주석 처리해뒀지만(최신 API가 필수 요구하지 않는 것으로 보임), 필요한
        환경을 위해 호출부에서 선택적으로 쓸 수 있게 헬퍼만 제공한다."""
        response = self._client.post(
            f"{self._base_url}{HASHKEY_PATH}",
            json=body,
            headers={
                "content-type": "application/json; charset=utf-8",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        hash_value = data.get("HASH")
        if not hash_value:
            raise KISAuthError(f"hashkey 응답에 HASH가 없습니다: {data}")
        return hash_value
