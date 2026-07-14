from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_container
from app.auth.security import create_access_token, verify_password
from app.dependencies import Container
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, container: Container = Depends(get_container)) -> LoginResponse:
    user = container.user_repo.get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    token = create_access_token(user.username, container.settings)
    return LoginResponse(access_token=token)
