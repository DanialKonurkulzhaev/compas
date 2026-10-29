from typing import Annotated
import uuid

from fastapi import Depends, Request

from src.exceptions import (
    IncorrectTokenException,
    IncorrectTokenHTTPException,
    NoAccessTokenHTTPException,
)
from src.services.auth import AuthService
from src.api.dependencies.db import DBDep
from src.config import settings


def get_token(request: Request) -> str:
    token = request.cookies.get("compas_access_token", None)
    if not token and settings.LEGACY_AUTH_COOKIES:
        token = request.cookies.get("access_token")
    if not token:
        raise NoAccessTokenHTTPException
    return token


async def get_current_user_id(db: DBDep, token: str = Depends(get_token)) -> uuid.UUID:
    try:
        data = AuthService().decode_token(token)
        user_id = uuid.UUID(str(data["user_id"]))
        if await db.users.get_one_or_none(id=user_id) is None:
            raise IncorrectTokenHTTPException
        return user_id
    except IncorrectTokenException:
        raise IncorrectTokenHTTPException
    except (KeyError, ValueError, TypeError):
        raise IncorrectTokenHTTPException


UserIdDep = Annotated[uuid.UUID, Depends(get_current_user_id)]
