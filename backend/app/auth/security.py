"""비밀번호 해시. 이 PoC는 인증 게이트가 없어(§0-17) 로그인/토큰 검증 로직은 없다 —
admin 계정 시드(app/dependencies.py)가 비밀번호를 평문으로 남기지 않기 위해서만 쓴다.
"""

from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
