import logging
import uuid
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from src.exceptions import ObjectNotFoundException, MyAppException
from src.models import ClientsOrm, UsersOrm
from src.schemas.psychologist import PsychologistResponseRequest
from src.services.base import BaseService

logger = logging.getLogger(__name__)


class ClientService(BaseService):
    async def get_your_psychologists(self, client_id: uuid.UUID):
        stmt = (
            select(UsersOrm)
            .join(ClientsOrm, ClientsOrm.mentor_id == UsersOrm.id)
            .where(
                ClientsOrm.client_id == client_id,
                ClientsOrm.status.is_(True),
                UsersOrm.role_id == 2,
            )
            .options(selectinload(UsersOrm.inquiries))
            .order_by(UsersOrm.username, UsersOrm.id)
        )
        result = await self.db.session.execute(stmt)
        items = [
            PsychologistResponseRequest.model_validate(user)
            for user in result.scalars().unique()
        ]
        return {"items": items, "total": len(items)}

    async def get_client(
        self, mentor_id: uuid.UUID, client_id: uuid.UUID | None = None
    ):
        try:
            if client_id is None:
                relations = await self.db.clients.get_filtered(
                    mentor_id=mentor_id, status=True
                )
                if not relations:
                    return []
                clients = []
                for relation in relations:
                    stmt = (
                        select(UsersOrm)
                        .where(UsersOrm.id == relation.client_id)
                        .options(selectinload(UsersOrm.inquiries))
                    )
                    result = await self.db.session.execute(stmt)
                    client = result.scalar_one_or_none()
                    if client:
                        clients.append(
                            {
                                "id": client.id,
                                "username": client.username,
                                "birth_date": client.birth_date,
                                "text": relation.text,
                                "gender": client.gender,
                                "inquiry": client.inquiries,
                            }
                        )
                return clients
            else:
                relation = await self.db.clients.get_one_or_none(
                    client_id=client_id, mentor_id=mentor_id, status=True
                )
                if not relation:
                    raise ObjectNotFoundException(
                        "Клиент не найден или не привязан к вам"
                    )
                stmt = (
                    select(UsersOrm)
                    .where(UsersOrm.id == client_id)
                    .options(selectinload(UsersOrm.inquiries))
                )
                result = await self.db.session.execute(stmt)
                client = result.scalar_one_or_none()
                if not client:
                    raise ObjectNotFoundException("Клиент не найден")
                return {
                    "id": client.id,
                    "username": client.username,
                    "birth_date": client.birth_date,
                    "text": relation.text,
                    "gender": client.gender,
                    "inquiry": client.inquiries,
                }
        except ObjectNotFoundException as ex:
            raise ex
        except Exception as ex:
            logger.error(f"Ошибка при получении клиента: {ex}")
            raise MyAppException()
