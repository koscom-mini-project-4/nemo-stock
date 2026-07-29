"""AI 클라이언트 인터페이스.

OpenAI 전용 로직을 서비스 코드(워크플로 초안 생성, 감성 점수화)에 노출하지 않기 위한 추상화.
추후 다른 LLM 제공자로 교체하려면 이 ABC만 구현하면 된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable


class AIUnavailableError(RuntimeError):
    """API 키 미설정 등으로 AI 호출이 불가능할 때 발생."""


class AIClient(ABC):
    @property
    @abstractmethod
    def available(self) -> bool: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def complete_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.2, purpose: str = "unknown"
    ) -> dict:
        """system/user 프롬프트로 LLM을 호출하고 JSON으로 파싱된 dict를 반환한다.
        available이 False인 상태에서 호출하면 AIUnavailableError를 발생시킨다.

        purpose: 어느 기능이 호출했는지 구분하는 자유 문자열(관리자 페이지 사용량 통계의
        목적별 집계에 쓰인다). 생략하면 "unknown"으로 기록된다 — 필수 아님.
        """

    @abstractmethod
    def complete_json_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        purpose: str = "unknown",
        on_chunk: Callable[[str], None] | None = None,
    ) -> dict:
        """complete_json과 완전히 동일한 계약(파싱된 dict 반환, available=False면
        AIUnavailableError)이지만, on_chunk가 주어지면 생성되는 원문 텍스트 조각을 JSON
        파싱 전에 실시간으로 넘겨준다(§0-18, "AI가 작성 중" 실시간 미리보기용). on_chunk가
        None이면 complete_json과 동작이 완전히 같다.
        """

    @abstractmethod
    def complete_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict],
        tool_executor: Callable[[str, dict], Any],
        temperature: float = 0.2,
        purpose: str = "unknown",
        max_rounds: int = 4,
    ) -> dict:
        """AI가 스스로 도구(함수)를 호출해 데이터를 보충할 수 있게 하는 다회 호출 버전(§0-9,
        app.nodes.ai.free_prompt에서 사용). tools는 OpenAI function-calling 스펙(list of
        {"type": "function", "function": {"name", "description", "parameters"}}).

        AI가 도구 호출을 요청하면 tool_executor(name, arguments)로 실행한 결과(JSON
        직렬화 가능해야 함)를 대화에 이어붙여 재호출한다. 더 이상 도구를 부르지 않거나
        max_rounds에 도달하면 도구 없이 마지막 1회를 호출해 최종 JSON을 강제로 받는다
        (무한 루프/과금 폭주 방지). complete_json과 동일하게 available=False면
        AIUnavailableError를 발생시킨다.
        """
