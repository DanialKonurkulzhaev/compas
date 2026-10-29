from src.api.dependencies.access import require_psychologist
import uuid
from fastapi import APIRouter, Query
from src.api.dependencies.db import DBDep
from src.api.dependencies.user_id import UserIdDep
from src.services.client import ClientService

router = APIRouter(prefix="/client", tags=["Клиент"])


@router.get("/get_your_psychologist", summary="Мои подтверждённые психологи")
async def get_your_psychologist(db: DBDep, user_id: UserIdDep):
    return await ClientService(db).get_your_psychologists(user_id)


@router.get("", summary="Получение всех клиентов или клиента по client_id")
async def get_client(
    db: DBDep,
    mentor_id: UserIdDep,
    client_id: uuid.UUID | None = Query(
        default=None, description="ID клиента (опционально)"
    ),
):
    await require_psychologist(db, mentor_id)
    return await ClientService(db).get_client(mentor_id, client_id)
