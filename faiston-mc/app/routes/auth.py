from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from ..config import settings

COOKIE_NAME = "faiston_mc_session"
_SALT = "faiston-mc-auth"


def _serializer() -> URLSafeTimedSerializer:
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY não configurado")
    return URLSafeTimedSerializer(settings.secret_key, salt=_SALT)


def _max_age_seconds() -> int:
    return settings.session_max_age_days * 24 * 3600


def set_session_cookie(response: Response) -> None:
    token = _serializer().dumps({"ok": True})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=_max_age_seconds(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def _is_valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=_max_age_seconds())
        return True
    except (BadSignature, SignatureExpired):
        return False


def require_auth(request: Request) -> None:
    if not _is_valid(request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Não autenticado")


router = APIRouter(prefix="/api", tags=["auth"])


class LoginBody(BaseModel):
    senha: str


@router.post("/login")
def login(body: LoginBody, response: Response):
    if not settings.app_password or not hmac.compare_digest(body.senha, settings.app_password):
        raise HTTPException(status_code=401, detail="Senha incorreta")
    set_session_cookie(response)
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(_: None = Depends(require_auth)):
    return {"ok": True}
