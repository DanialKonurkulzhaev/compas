"""Тестовая SQLite в памяти; PostgreSQL ARRAY заменяется на JSON на время теста."""

import json
import uuid
import os
from types import SimpleNamespace
from functools import lru_cache

os.environ["MODE"] = "TEST"
os.environ["DB_PASS"] = "isolated-test-only-password"
os.environ["JWT_SECRET_KEY"] = "compas-test-access-secret-never-for-production"
os.environ["JWT_REFRESH_SECRET_KEY"] = "compas-test-refresh-secret-never-for-production"
os.environ["DATA_ENCRYPTION_KEY"] = "OGl98HzdujCEwk87WtUh8-F7ur_MatPs1HZPGe0cg6I="

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, JSON, ARRAY, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.main import app
from src.api.dependencies.db import get_db
from src.utils.db_manager import DBManager
from src.models import UsersOrm
from src.services.auth import AuthService
from src.services.catalog import seed_catalog


@lru_cache
def test_password_hash():
    return AuthService().hash_password("CompasTest123!")


class AsyncSessionAdapter:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def get(self, model, pk):
        return self.session.get(model, pk)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def close(self):
        pass

    async def delete(self, item):
        self.session.delete(item)

    def add(self, item):
        self.session.add(item)


@pytest.fixture
def sandbox():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        json_serializer=lambda value: json.dumps(value, default=str),
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    arrays = [
        (column, column.type)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, ARRAY)
    ]
    for column, old_type in arrays:
        column.type = JSON()
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    adapter = AsyncSessionAdapter(session)
    ids = {}
    for label, role in [
        ("admin", 0),
        ("user", 1),
        ("psychologist", 2),
        ("stranger", 1),
        ("other_psychologist", 2),
    ]:
        uid = uuid.uuid4()
        ids[label] = uid
        session.add(
            UsersOrm(
                id=uid,
                username=label,
                email=f"{label}@example.com",
                gender="male",
                hashed_password=test_password_hash(),
                role_id=role,
            )
        )
    session.commit()

    async def db_override():
        async with DBManager(lambda: adapter) as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    client = TestClient(app)

    def login(label):
        client.cookies.clear()
        response = client.post(
            "/auth/login",
            json={"email": f"{label}@example.com", "password": "CompasTest123!"},
        )
        assert response.status_code == 200, response.text

    async def seed():
        async with DBManager(lambda: adapter) as db:
            return await seed_catalog(db)

    try:
        yield SimpleNamespace(
            http=client,
            ids=ids,
            session=session,
            adapter=adapter,
            login=login,
            seed=seed,
        )
    finally:
        client.close()
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()
        for column, old_type in arrays:
            column.type = old_type
