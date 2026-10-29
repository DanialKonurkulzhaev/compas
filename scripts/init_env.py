"""Создание .env для локального запуска."""

from pathlib import Path
import secrets
from cryptography.fernet import Fernet

target = Path(__file__).resolve().parents[1] / ".env"
content = "\n".join(
    [
        "MODE=LOCAL",
        "DB_HOST=localhost",
        "DB_PORT=5544",
        "DB_USER=compas",
        "DB_NAME=compas",
        "DB_PASS=" + secrets.token_urlsafe(32),
        "JWT_SECRET_KEY=" + secrets.token_urlsafe(48),
        "JWT_REFRESH_SECRET_KEY=" + secrets.token_urlsafe(48),
        "DATA_ENCRYPTION_KEY=" + Fernet.generate_key().decode(),
        "COOKIE_SECURE=false",
        "ALLOWED_ORIGINS=[]",
        "YANDEX_CLIENT_ID=",
        "YANDEX_CLIENT_SECRET=",
        "YANDEX_REDIRECT_URI=http://127.0.0.1:8001/yandex/callback/code",
        "",
    ]
)
try:
    with target.open("x", encoding="utf-8") as handle:
        handle.write(content)
    target.chmod(0o600)
    print("Created compas/.env with independent secrets")
except FileExistsError:
    print(".env already exists; kept unchanged")
