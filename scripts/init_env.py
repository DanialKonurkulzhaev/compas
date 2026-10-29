"""Создание .env для локального запуска."""

import argparse
import base64
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env"
    )
    args = parser.parse_args()
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
            "DATA_ENCRYPTION_KEY="
            + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "COOKIE_SECURE=false",
            "LEGACY_AUTH_COOKIES=true",
            'ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]',
            "FRONTEND_URL=http://localhost:3000",
            "YANDEX_CLIENT_ID=",
            "YANDEX_CLIENT_SECRET=",
            "YANDEX_REDIRECT_URI=http://localhost:8001/yandex/callback/code",
            "",
        ]
    )
    try:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(content)
        args.output.chmod(0o600)
        print("Created .env with independent secrets")
    except FileExistsError:
        print(".env already exists; kept unchanged")


if __name__ == "__main__":
    main()
