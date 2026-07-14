"""Toss증권 Open API OAuth2 Client Credentials 토큰 발급/캐싱.

market_data/toss_adapter.py와 broker/toss_adapter.py가 공유한다.

※ 미검증(실험적): developers.tossinvest.com은 사전신청 기반 단계적 오픈 중으로,
현재 이 프로젝트에는 승인된 클라이언트 자격증명이 없어 아래 토큰 엔드포인트 경로/응답
필드명은 공개된 요약 정보("OAuth 2.0 Client Credentials Grant로 발급받은 access token 사용")를
바탕으로 한 최선 추정치다. 실제 키 발급 후 공식 OpenAPI 명세로 교체해야 한다.
"""

from __future__ import annotations

import time

import httpx

TOKEN_PATH = "/oauth2/token"  # TODO: 실제 키 발급 후 공식 명세로 검증/교체


class TossAuthError(RuntimeError):
    pass


class TossOAuthTokenProvider:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        base_url: str,
        http_client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout)
        self._cached_token: str | None = None
        self._expires_at: float = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "TossOAuthTokenProvider":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_token(self) -> str:
        now = time.monotonic()
        if self._cached_token and now < self._expires_at:
            return self._cached_token

        response = self._client.post(
            f"{self._base_url}{TOKEN_PATH}",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise TossAuthError(f"토큰 발급 응답에 access_token이 없습니다: {data}")

        expires_in = int(data.get("expires_in", 3600))
        self._cached_token = token
        self._expires_at = now + max(expires_in - 30, 0)  # 30초 여유를 두고 만료 처리
        return token

    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}
