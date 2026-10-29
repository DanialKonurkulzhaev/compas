"""Проверки технических метрик; команды запуска — в docs/metrics.md.

COMPAS_METRICS_URL включает GET-нагрузку на указанный стенд.
COMPAS_METRICS_BACKUP включает восстановление дампа в отдельную БД.
Без этих переменных выполняются только изолированные проверки.
"""

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, TimeoutError as PoolTimeout
from sqlalchemy.pool import QueuePool

from src.config import ROOT, settings
from src.main import app
from src.models import ClientsOrm, UsersOrm
from src.services.auth import AuthService
from src.utils.db_manager import DBManager
from src.utils.encryption import decrypt_from_storage, encrypt_for_storage


def test_metric_6_pool_exhaustion_times_out_then_recovers():
    """Занятый пул отклоняет запрос по таймауту и освобождается после close."""
    engine = create_engine(
        "sqlite://",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.05,
    )
    try:
        with engine.connect():
            with pytest.raises(PoolTimeout):
                with engine.connect():
                    pytest.fail("Pool exceeded its configured limit")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        engine.dispose()


def test_metric_6_requests_have_timing_and_unique_trace_ids(sandbox):
    ids = set()
    for _ in range(20):
        response = sandbox.http.get("/health/live")
        assert response.status_code == 200
        ids.add(response.headers["X-Request-ID"])
        milliseconds = float(response.headers["Server-Timing"].split("dur=")[1])
        assert milliseconds >= 0
    assert len(ids) == 20


def test_metric_7_readiness_reports_outage_and_recovery(sandbox, monkeypatch):
    """При сбое БД readiness возвращает 503, liveness остаётся доступен."""
    connection = AsyncMock()
    connect = AsyncMock()
    connect.__aenter__.side_effect = ConnectionError("Test database unavailable")
    engine = type("Engine", (), {"connect": lambda self: connect})()
    monkeypatch.setattr("src.main.engine", engine)
    response = sandbox.http.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert sandbox.http.get("/health/live").status_code == 200
    connect.__aenter__.side_effect = None
    connect.__aenter__.return_value = connection
    assert sandbox.http.get("/health/ready").json() == {"status": "ready"}
    connection.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_metric_7_failed_transaction_does_not_leave_partial_data(sandbox):
    uid = uuid.uuid4()
    with pytest.raises(RuntimeError, match="interrupted"):
        async with DBManager(lambda: sandbox.adapter) as db:
            await db.add(
                UsersOrm(
                    id=uid,
                    username="Temporary",
                    email="temporary@example.com",
                    gender="male",
                    role_id=1,
                )
            )
            await db.session.flush()
            raise RuntimeError("interrupted")
    assert sandbox.session.get(UsersOrm, uid) is None
    assert sandbox.session.scalar(select(func.count()).select_from(UsersOrm)) == 5


def test_metric_9_auth_session_can_be_used_by_another_http_client(sandbox):
    """Один токен работает в разных HTTP-клиентах."""
    sandbox.login("user")
    token = sandbox.http.cookies.get("compas_access_token")
    with TestClient(app) as second:
        second.cookies.set("compas_access_token", token)
        response = second.get("/auth/me")
        assert response.status_code == 200
        assert response.json()["id"] == str(sandbox.ids["user"])


def test_metric_10_admin_can_add_edit_and_delete_catalog_item(sandbox):
    sandbox.login("admin")
    response = sandbox.http.post(
        "/tests/",
        json={
            "title": "Metrics demo",
            "description": "Description",
            "short_desc": "Short description",
            "link": "/images/example.png",
        },
    )
    assert response.status_code == 200, response.text
    test_id = response.json()["id"]
    response = sandbox.http.patch(f"/tests/{test_id}", json={"title": "Updated"})
    assert response.status_code == 200, response.text
    assert sandbox.http.get(f"/tests/{test_id}").json()["title"] == "Updated"
    assert sandbox.http.delete(f"/tests/{test_id}").status_code == 204
    assert sandbox.http.get(f"/tests/{test_id}").status_code == 404


@pytest.mark.parametrize("failure", ["duplicate_pair", "missing_user"])
def test_metric_11_database_rejects_invalid_client_links(sandbox, failure):
    def link(client_id):
        return ClientsOrm(
            id=uuid.uuid4(),
            client_id=client_id,
            mentor_id=sandbox.ids["psychologist"],
            text="Metrics",
            status=True,
        )

    sandbox.session.add(link(sandbox.ids["user"]))
    sandbox.session.commit()
    sandbox.session.add(
        link(sandbox.ids["user"] if failure == "duplicate_pair" else uuid.uuid4())
    )
    with pytest.raises(IntegrityError):
        sandbox.session.commit()
    sandbox.session.rollback()
    assert sandbox.session.scalar(select(func.count()).select_from(ClientsOrm)) == 1


def test_metric_13_password_hash_is_salted_and_verifiable():
    auth = AuthService()
    password = "MetricsPassword123!"
    first, second = auth.hash_password(password), auth.hash_password(password)
    assert first != second and password not in first
    assert auth.verify_password(password, first)
    assert not auth.verify_password("WrongPassword123!", first)


def test_metric_13_encryption_roundtrip_and_ciphertext_integrity():
    first, second = encrypt_for_storage(42.5), encrypt_for_storage(42.5)
    assert first != second
    assert decrypt_from_storage(first, float) == 42.5
    # Меняем содержимое токена, сохраняя base64 padding.
    index = 30
    tampered = (
        first[:index] + ("A" if first[index] != "A" else "B") + first[index + 1 :]
    )
    with pytest.raises(ValueError):
        decrypt_from_storage(tampered, float)


def test_metric_13_refresh_and_expired_tokens_cannot_access_profile(sandbox):
    _, refresh = AuthService().create_tokens(
        {
            "user_id": str(sandbox.ids["user"]),
            "role_id": 1,
        }
    )
    expired = jwt.encode(
        {
            "user_id": str(sandbox.ids["user"]),
            "role_id": 1,
            "exp": 1,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    for token in (refresh, expired):
        sandbox.http.cookies.clear()
        sandbox.http.cookies.set("compas_access_token", token)
        assert sandbox.http.get("/auth/me").status_code == 401


def test_metric_13_normal_user_cannot_edit_test_catalog(sandbox):
    sandbox.login("user")
    response = sandbox.http.post(
        "/tests/",
        json={
            "title": "Forbidden",
            "description": "Description",
            "short_desc": "Short",
            "link": "/images/example.png",
        },
    )
    assert response.status_code == 403


def test_metric_13_request_logs_do_not_include_credentials(sandbox, caplog):
    caplog.set_level(logging.INFO, logger="compas")
    sandbox.login("user")
    token = sandbox.http.cookies.get("compas_access_token")
    assert sandbox.http.get("/auth/me").status_code == 200
    assert token not in caplog.text
    assert "CompasTest123!" not in caplog.text
    assert "user@example.com" not in caplog.text


def test_metric_6_live_get_workload(tmp_path, record_property):
    url = os.environ.get("COMPAS_METRICS_URL")
    if not url:
        pytest.skip("Set COMPAS_METRICS_URL to opt into GET load on a test server")
    output = tmp_path / "load.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/load.py"),
            "--url",
            url,
            "--requests",
            "100",
            "--concurrency",
            "10",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    print("\nMetric 6, GET /tests:", json.dumps(report, ensure_ascii=False))
    record_property("metric_6_get_load", json.dumps(report))
    assert report["requests"] == 100
    assert report["statuses"] == {"200": 100}, report
    # Порог скорости зависит от стенда; здесь проверяются только HTTP-ошибки.


def test_metric_7_postgres_backup_restores_in_new_database(record_property):
    value = os.environ.get("COMPAS_METRICS_BACKUP")
    if not value:
        pytest.skip("Set COMPAS_METRICS_BACKUP to opt into restoring a dump in Docker")
    backup = Path(value).resolve()
    assert backup.is_file(), "Backup file not found"
    # Compose должен прочитать .env проекта, а не тестовые секреты из conftest.
    env = os.environ.copy()
    for key in (
        "MODE",
        "DB_PASS",
        "JWT_SECRET_KEY",
        "JWT_REFRESH_SECRET_KEY",
        "DATA_ENCRYPTION_KEY",
    ):
        env.pop(key, None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/backup.py"),
            "restore-check",
            str(backup),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, "Restore failed; inspect Docker/PostgreSQL logs"
    assert "Restored into independent database:" in result.stdout
    database = result.stdout.rsplit("Restored into independent database:", 1)[1].strip()
    record_property("metric_7_restored_database", database)
    print("\nMetric 7: restored into", database)
