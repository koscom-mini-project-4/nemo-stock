"""AI 클라이언트 인터페이스.

OpenAI 전용 로직을 서비스 코드(워크플로 초안 생성, 감성 점수화)에 노출하지 않기 위한 추상화.
추후 다른 LLM 제공자로 교체하려면 이 ABC만 구현하면 된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


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
    def complete_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        """system/user 프롬프트로 LLM을 호출하고 JSON으로 파싱된 dict를 반환한다.
        available이 False인 상태에서 호출하면 AIUnavailableError를 발생시킨다.
        """
