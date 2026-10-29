"""Обмен кода Яндекса на профиль, вход и привязка аккаунта."""

import uuid

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.enums import RoleEnum
from src.models.users import UsersOrm
from src.schemas.yandex import YandexProfile
from src.services.auth import AuthService
from src.services.base import BaseService

AUTH_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"
PROFILE_URL = "https://login.yandex.ru/info"


def ensure_configured(*, exchange=False):
    if not settings.YANDEX_CLIENT_ID or (
        exchange and not settings.YANDEX_CLIENT_SECRET
    ):
        raise HTTPException(
            503,
            "Вход через Яндекс не настроен: заполните YANDEX_CLIENT_ID и YANDEX_CLIENT_SECRET в .env",
        )


async def exchange_code(code: str, verifier: str) -> str:
    ensure_configured(exchange=True)
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.YANDEX_CLIENT_ID,
                    "client_secret": settings.YANDEX_CLIENT_SECRET,
                    "redirect_uri": settings.YANDEX_REDIRECT_URI,
                    "code_verifier": verifier,
                },
            )
        if response.status_code in (400, 401):
            raise HTTPException(400, "Яндекс отклонил код авторизации")
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError("missing token")
        return token
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Не удалось получить ответ от Яндекса") from None


async def get_yandex_user(token: str) -> YandexProfile:
    ensure_configured()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get(
                PROFILE_URL,
                params={"format": "json"},
                headers={"Authorization": f"OAuth {token}"},
            )
        if response.status_code in (400, 401, 403):
            raise HTTPException(401, "Яндекс отклонил OAuth-токен")
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Не удалось получить профиль Яндекса") from None
    try:
        profile = YandexProfile.model_validate(data)
    except ValidationError:
        raise HTTPException(
            400,
            "Яндекс не передал ID, email или данные приложения; проверьте разрешения login:email и login:info",
        ) from None
    if profile.client_id != settings.YANDEX_CLIENT_ID:
        raise HTTPException(401, "OAuth-токен выпущен для другого приложения")
    return profile


class YandexService(BaseService):
    async def login(self, profile: YandexProfile):
        user = (
            await self.db.session.execute(
                select(UsersOrm).where(UsersOrm.yandex_id == profile.id)
            )
        ).scalar_one_or_none()
        if user is None:
            email = str(profile.default_email).lower()
            existing = (
                await self.db.session.execute(
                    select(UsersOrm.id).where(func.lower(UsersOrm.email) == email)
                )
            ).first()
            if existing:
                raise HTTPException(
                    409,
                    "Аккаунт с таким email уже существует. Сначала войдите обычным способом и привяжите Яндекс через POST /yandex/link",
                )
            user = UsersOrm(
                id=uuid.uuid4(),
                email=email,
                username=profile.display_name or profile.login or "Yandex user",
                gender=profile.sex or "not specified",
                hashed_password=None,
                role_id=RoleEnum.USER,
                yandex_id=profile.id,
            )
            self.db.session.add(user)
            try:
                await self.db.commit()
            except IntegrityError:
                await self.db.rollback()
                raise HTTPException(409, "Аккаунт уже создан; повторите вход") from None
        return AuthService().create_tokens(
            {"user_id": str(user.id), "role_id": user.role_id}
        )

    async def link(self, user_id: uuid.UUID, profile: YandexProfile):
        user = await self.db.session.get(UsersOrm, user_id)
        if user is None:
            raise HTTPException(401, "Требуется авторизация")
        if user.email.lower() != str(profile.default_email).lower():
            raise HTTPException(
                409, "Для привязки email аккаунта и Яндекса должны совпадать"
            )
        if user.yandex_id and user.yandex_id != profile.id:
            raise HTTPException(409, "К аккаунту уже привязан другой Яндекс ID")
        user.yandex_id = profile.id
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                409, "Этот Яндекс ID уже привязан к другому аккаунту"
            ) from None
        return {"status": "OK"}
