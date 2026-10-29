from fastapi import Response

from src.config import settings


def set_auth_cookies(response: Response, access: str, refresh: str):
    values = [("compas_access_token", access), ("compas_refresh_token", refresh)]
    if settings.LEGACY_AUTH_COOKIES:
        values.extend([("access_token", access), ("refresh_token", refresh)])
    for name, value in values:
        response.set_cookie(
            name, value, httponly=True, secure=settings.COOKIE_SECURE, samesite="lax"
        )


def delete_auth_cookies(response: Response):
    names = ["compas_access_token", "compas_refresh_token"]
    if settings.LEGACY_AUTH_COOKIES:
        names.extend(["access_token", "refresh_token"])
    for name in names:
        response.delete_cookie(name)
