"""Заявки и связь клиента с психологом обновляются в одной транзакции."""

import uuid
from sqlalchemy import select
from fastapi import HTTPException
from src.models.application import ApplicationOrm
from src.models.clients import ClientsOrm
from src.models.users import UsersOrm
from src.schemas.application import ApplicationResponse
from src.services.base import BaseService
from src.enums import RoleEnum


class ApplicationService(BaseService):
    async def _owned(self, app_id, user_id, *, recipient=False):
        stmt = select(ApplicationOrm).where(ApplicationOrm.id == app_id)
        if recipient:
            stmt = stmt.where(ApplicationOrm.manager_id == user_id)
        else:
            stmt = stmt.where(
                (ApplicationOrm.manager_id == user_id)
                | (ApplicationOrm.client_id == user_id)
            )
        item = (
            await self.db.session.execute(stmt.with_for_update())
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(404, "Заявка не найдена")
        return item

    async def get_applications(self, user_id):
        stmt = (
            select(ApplicationOrm)
            .where(
                (ApplicationOrm.manager_id == user_id)
                | (ApplicationOrm.client_id == user_id)
            )
            .order_by(ApplicationOrm.created_at.desc())
        )
        return [
            ApplicationResponse.model_validate(x, from_attributes=True)
            for x in (await self.db.session.execute(stmt)).scalars()
        ]

    async def get_application(self, app_id, user_id):
        return ApplicationResponse.model_validate(
            await self._owned(app_id, user_id), from_attributes=True
        )

    async def delete_application(self, app_id, user_id):
        item = await self._owned(app_id, user_id)
        relation = (
            await self.db.session.execute(
                select(ClientsOrm).where(
                    ClientsOrm.client_id == item.client_id,
                    ClientsOrm.mentor_id == item.manager_id,
                )
            )
        ).scalar_one_or_none()
        if relation:
            relation.status = False
        await self.db.session.delete(item)
        await self.db.commit()
        return {"status": "OK"}

    async def add_application(self, data, user_id):
        mentor = await self.db.session.get(UsersOrm, data.manager_id)
        if (
            mentor is None
            or mentor.role_id != RoleEnum.PSYCHOLOGIST
            or mentor.id == user_id
        ):
            raise HTTPException(400, "Укажите психолога")
        existing = (
            await self.db.session.execute(
                select(ApplicationOrm).where(
                    ApplicationOrm.client_id == user_id,
                    ApplicationOrm.manager_id == mentor.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return {"app_id": str(existing.id)}
        item = ApplicationOrm(
            client_id=user_id,
            manager_id=mentor.id,
            text=data.text,
            inquiry=data.inquiry or [],
            status=False,
        )
        self.db.session.add(item)
        await self.db.commit()
        return {"app_id": str(item.id)}

    async def update_application_status(self, app_id, user_id):
        item = await self._owned(app_id, user_id, recipient=True)
        user = await self.db.session.get(UsersOrm, user_id)
        if user is None or user.role_id != RoleEnum.PSYCHOLOGIST:
            raise HTTPException(403, "Доступ только психологу")
        item.status = not item.status
        relation = (
            await self.db.session.execute(
                select(ClientsOrm).where(
                    ClientsOrm.client_id == item.client_id,
                    ClientsOrm.mentor_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if relation is None:
            relation = ClientsOrm(
                id=uuid.uuid4(),
                client_id=item.client_id,
                mentor_id=user_id,
                text=item.text,
                status=item.status,
            )
            self.db.session.add(relation)
        else:
            relation.status = item.status
        await self.db.commit()
        return {"status": "OK", "message": "Статус заявки обновлен"}
