import json
import subprocess
import sys
import uuid
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from dotenv import dotenv_values
import jwt

from src.api import yandex_auth
from src.config import ROOT, settings
from src.models import ClientsOrm
from src.schemas.yandex import YandexProfile
from src.services.auth import AuthService


def test_registration_returns_profile_and_tokens_without_password(sandbox):
    response = sandbox.http.post(
        "/auth/register",
        json={
            "email": "frontend@example.com",
            "username": "Frontend",
            "gender": "",
            "birth_date": "2000-01-01",
            "city": "",
            "phone_number": "",
            "password": "Frontend123!",
            "confirm_password": "Frontend123!",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == "frontend@example.com"
    assert data["username"] == "Frontend" and data["role_id"] == 1
    uuid.UUID(data["id"])
    assert AuthService().decode_token(data["access_token"])["user_id"] == data["id"]
    assert data["refresh_token"]
    assert "hashed_password" not in data and "password" not in data


def test_bff_can_forward_legacy_cookie_and_refresh_it(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_AUTH_COOKIES", True)
    sandbox.login("user")
    access = sandbox.http.cookies.get("access_token")
    refresh = sandbox.http.cookies.get("refresh_token")
    sandbox.http.cookies.clear()
    # Next.js BFF forwards its own access_token cookie, not the API Set-Cookie.
    response = sandbox.http.get(
        "/auth/me", headers={"Cookie": f"access_token={access}"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(sandbox.ids["user"])
    sandbox.http.cookies.clear()
    response = sandbox.http.post("/auth/refresh-token", json={"refresh_token": refresh})
    assert response.status_code == 200
    assert response.cookies["access_token"] == response.json()["access_token"]
    assert response.cookies["compas_access_token"] == response.json()["access_token"]
    assert sandbox.http.post("/auth/logout").status_code == 200
    assert sandbox.http.get("/auth/me").status_code == 401


def test_legacy_cookie_from_another_project_is_rejected(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_AUTH_COOKIES", True)
    foreign = jwt.encode(
        {"user_id": str(sandbox.ids["user"]), "role_id": 0},
        "foreign-project-key-that-must-not-be-trusted",
        algorithm="HS256",
    )
    assert (
        sandbox.http.get(
            "/auth/me", headers={"Cookie": f"access_token={foreign}"}
        ).status_code
        == 401
    )


def test_compas_cookie_has_priority_over_legacy_cookie(sandbox, monkeypatch):
    monkeypatch.setattr(settings, "LEGACY_AUTH_COOKIES", True)
    own, _ = AuthService().create_tokens(
        {"user_id": str(sandbox.ids["user"]), "role_id": 1}
    )
    other, _ = AuthService().create_tokens(
        {"user_id": str(sandbox.ids["stranger"]), "role_id": 1}
    )
    response = sandbox.http.get(
        "/auth/me",
        headers={"Cookie": f"compas_access_token={own}; access_token={other}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(sandbox.ids["user"])


def test_my_psychologists_only_returns_accepted_links_for_current_user(sandbox):
    assert sandbox.http.get("/client/get_your_psychologist").status_code == 401
    for label, mentor, accepted in [
        ("user", "psychologist", True),
        ("user", "other_psychologist", False),
        ("stranger", "other_psychologist", True),
    ]:
        sandbox.session.add(
            ClientsOrm(
                id=uuid.uuid4(),
                client_id=sandbox.ids[label],
                mentor_id=sandbox.ids[mentor],
                status=accepted,
                text="Request",
            )
        )
    sandbox.session.commit()
    sandbox.login("user")
    response = sandbox.http.get("/client/get_your_psychologist")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == [
        str(sandbox.ids["psychologist"])
    ]
    sandbox.login("stranger")
    assert sandbox.http.get("/client/get_your_psychologist").json()["items"][0][
        "id"
    ] == str(sandbox.ids["other_psychologist"])


def test_oauth_redirects_to_configured_frontend_without_tokens_in_url(
    sandbox, monkeypatch
):
    monkeypatch.setattr(settings, "YANDEX_CLIENT_ID", "compas-test")
    monkeypatch.setattr(settings, "YANDEX_CLIENT_SECRET", "compas-test-secret")
    monkeypatch.setattr(settings, "LEGACY_AUTH_COOKIES", True)
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000/")

    async def exchange(code, verifier):
        return "provider-token"

    async def profile(token):
        return YandexProfile(
            id="frontend-yandex",
            client_id="compas-test",
            default_email="oauth.frontend@example.com",
        )

    monkeypatch.setattr(yandex_auth, "exchange_code", exchange)
    monkeypatch.setattr(yandex_auth, "get_yandex_user", profile)
    start = sandbox.http.get("/yandex/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    response = sandbox.http.get(
        "/yandex/callback/code",
        params={
            "code": "code",
            "state": state,
            "redirect": "https://untrusted.example/",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:3000/"
    assert (
        "access_token" in response.cookies and "compas_access_token" in response.cookies
    )
    assert "code=" not in response.headers["location"]
    assert "token" not in response.headers["location"]
    assert sandbox.http.get("/auth/me").status_code == 200
    # Compatibility mode does not permit the old unprotected code-only exchange.
    assert (
        sandbox.http.get(
            "/yandex/callback/code", params={"code": "another"}
        ).status_code
        == 400
    )


def test_init_env_uses_only_stdlib_and_preserves_existing_secrets(tmp_path):
    target = tmp_path / ".env"
    command = [
        sys.executable,
        "-S",
        str(ROOT / "scripts/init_env.py"),
        "--output",
        str(target),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    values = dotenv_values(target)
    assert (
        values["DB_PASS"]
        and values["JWT_SECRET_KEY"] != values["JWT_REFRESH_SECRET_KEY"]
    )
    Fernet(values["DATA_ENCRYPTION_KEY"].encode())
    assert "http://localhost:3000" in json.loads(values["ALLOWED_ORIGINS"])
    saved = target.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert target.read_bytes() == saved
    assert "kept unchanged" in second.stdout
    assert values["DB_PASS"] not in first.stdout + second.stdout


def test_new_env_validates_as_compas_configuration(tmp_path):
    from src.config import Settings

    target = tmp_path / ".env"
    subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "scripts/init_env.py"),
            "--output",
            str(target),
        ],
        check=True,
        capture_output=True,
    )
    config = Settings(_env_file=target)
    assert config.LEGACY_AUTH_COOKIES
    assert str(config.FRONTEND_URL) == "http://localhost:3000/"
