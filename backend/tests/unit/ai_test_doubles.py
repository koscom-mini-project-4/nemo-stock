"""테스트 전용 AIClient/NewsTrader 더블. 실제 OpenAI 호출/크롤링 없이 AI 관련 로직을 검증하기 위해 사용한다."""

from __future__ import annotations

from typing import Any

from app.ai.base import AIClient, AIUnavailableError


class FakeAIClient(AIClient):
    def __init__(self, responses: list[dict] | None = None, model: str = "fake-model", available: bool = True):
        self._responses = list(responses or [])
        self._model = model
        self._available = available
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._available

    @property
    def model_name(self) -> str:
        return self._model

    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        if not self._available:
            raise AIUnavailableError("fake client unavailable")
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("FakeAIClient: 더 이상 준비된 응답이 없습니다.")
        return self._responses.pop(0)


class FakeNewsTrader:
    """app.vendor.news_classifier.NewsTrader 더블. stock/sector/macro가 미리 준비된 결과를
    반환한다(name -> 결과 dict). 없는 키는 라이브러리의 "데이터 없음" 동작(평균 0, 판정 n)을
    흉내낸다."""

    def __init__(self, results: dict[str, dict[str, Any]] | None = None):
        self._results = dict(results or {})
        self.calls: list[tuple[str, str, int | None]] = []
        self.update_calls: list[bool] = []
        self.closed = False

    def _lookup(self, axis: str, name: str, period: int | None) -> dict[str, Any]:
        self.calls.append((axis, name, period))
        return self._results.get(name, {"판정": "n", "평균": 0.0, "클러스터수": 0})

    def stock(self, name: str, start: str | None = None, period: int | None = None) -> dict:
        return self._lookup("stock", name, period)

    def sector(self, name: str, start: str | None = None, period: int | None = None) -> dict:
        return self._lookup("sector", name, period)

    def macro(self, name: str, start: str | None = None, period: int | None = None) -> dict:
        return self._lookup("macro", name, period)

    def update(self, force: bool = False, progress=None) -> dict:
        self.update_calls.append(force)
        return {"건너뜀": False, "수집": 0, "분류": 0, "미분류잔여": 0, "삭제클러스터": 0}

    def close(self) -> None:
        self.closed = True


class FakeNewsTraderFactory:
    """Container.news_trader_factory 대체용. 항상 같은 FakeNewsTrader 인스턴스를 반환하고
    auto_update 인자 호출 이력을 기록한다."""

    def __init__(self, trader: FakeNewsTrader):
        self.trader = trader
        self.auto_update_calls: list[bool] = []

    def __call__(self, auto_update: bool = True) -> FakeNewsTrader:
        self.auto_update_calls.append(auto_update)
        return self.trader
