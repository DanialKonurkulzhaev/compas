import base64
import hashlib
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadData, URLSafeTimedSerializer

from src.api.dependencies.db import DBDep
from src.api.dependencies.user_id import UserIdDep
from src.config import settings
from src.schemas.users import TokenResponse
from src.schemas.yandex import YandexTokenRequest
from src.services.yandex import (
    AUTH_URL,
    YandexService,
    ensure_configured,
    exchange_code,
    get_yandex_user,
)
from src.utils.auth_cookies import set_auth_cookies

router = APIRouter(prefix="/yandex", tags=["Авторизация Яндекс"])
STATE_COOKIE = "compas_yandex_state"
MAX_AGE = 600


def state_serializer():
    return URLSafeTimedSerializer(
        settings.JWT_SECRET_KEY, salt="compas-yandex-oauth-v1"
    )


def token_response(tokens, redirect_to_frontend=False):
    access, refresh = tokens
    response = (
        RedirectResponse(str(settings.FRONTEND_URL), status_code=303)
        if redirect_to_frontend and settings.FRONTEND_URL
        else Response(
            content=TokenResponse(
                access_token=access, refresh_token=refresh
            ).model_dump_json(),
            media_type="application/json",
        )
    )
    set_auth_cookies(response, access, refresh)
    response.delete_cookie(STATE_COOKIE, path="/yandex")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get(
    "/login",
    summary="Начать вход через Яндекс",
    description="Открывайте этот адрес в браузере. Требует настроек OAuth в .env.",
)
async def yandex_login():
    ensure_configured(exchange=True)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.YANDEX_CLIENT_ID,
            "redirect_uri": settings.YANDEX_REDIRECT_URI,
            "scope": "login:email login:info",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    response = RedirectResponse(AUTH_URL + "?" + query, status_code=302)
    response.set_cookie(
        STATE_COOKIE,
        state_serializer().dumps({"state": state, "verifier": verifier}),
        max_age=MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/yandex",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/callback/code",
    response_model=TokenResponse,
    summary="Завершить вход по коду Яндекса",
)
async def yandex_callback_code(
    request: Request,
    db: DBDep,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
):
    ensure_configured(exchange=True)
    try:
        saved = state_serializer().loads(
            request.cookies.get(STATE_COOKIE, ""), max_age=MAX_AGE
        )
        if (
            not isinstance(saved, dict)
            or not state
            or not secrets.compare_digest(saved.get("state", ""), state)
        ):
            raise BadData("invalid state")
        verifier = saved["verifier"]
    except (BadData, KeyError, TypeError):
        raise HTTPException(
            400,
            "Сессия входа Яндекса истекла или state не совпадает. Начните вход заново",
        ) from None
    if error or not code:
        response = Response(
            content='{"detail":"Вход через Яндекс отменён или код не получен"}',
            status_code=400,
            media_type="application/json",
        )
        response.delete_cookie(STATE_COOKIE, path="/yandex")
        return response
    token = await exchange_code(code, verifier)
    profile = await get_yandex_user(token)
    return token_response(
        await YandexService(db).login(profile), redirect_to_frontend=True
    )


@router.post(
    "/callback/token",
    response_model=TokenResponse,
    summary="Войти по OAuth-токену Яндекса",
    description="Токен передаётся в JSON-теле, не в URL. Проверяется приложение, выдавшее токен.",
)
async def yandex_callback_token(data: YandexTokenRequest, db: DBDep):
    profile = await get_yandex_user(data.token)
    return token_response(await YandexService(db).login(profile))


@router.post("/link", summary="Привязать Яндекс к своему аккаунту")
async def yandex_link(data: YandexTokenRequest, db: DBDep, user_id: UserIdDep):
    profile = await get_yandex_user(data.token)
    return await YandexService(db).link(user_id, profile)
