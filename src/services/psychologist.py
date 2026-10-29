import logging
import uuid
from datetime import datetime
from typing import Optional, Any, Dict, List
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from src.exceptions import (
    InternalErrorHTTPException,
    ObjectNotFoundHTTPException,
    ObjectNotFoundException,
    MyAppException,
)
from src.models import UsersOrm, user_inquiry
from src.models.inquiry import InquiryOrm
from src.schemas.psychologist import (
    BecomePsychologistRequest,
    InquiryAddRequest,
    PsychologistResponseRequest,
)
from src.services.base import BaseService

logger = logging.getLogger(__name__)


class PsychologistService(BaseService):
    async def add_inquiry(self, data: InquiryAddRequest):
        try:
            stmt = select(InquiryOrm).where(InquiryOrm.text == data.text)
            result = await self.db.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing
            new_inquiry = InquiryOrm(text=data.text)
            self.db.session.add(new_inquiry)
            await self.db.session.commit()
            await self.db.session.refresh(new_inquiry)
            return new_inquiry
        except Exception as e:
            logger.debug(str(e))
            await self.db.rollback()
            raise InternalErrorHTTPException()

    async def get_inquiry(self):
        try:
            return await self.db.inquiry.get_all()
        except Exception as e:
            logger.debug(str(e))
            raise InternalErrorHTTPException()

    async def delete_inquiry(self, inquiry_id):
        try:
            return await self.db.inquiry.delete(id=inquiry_id)
        except Exception as e:
            logger.debug(str(e))
            raise InternalErrorHTTPException()

    async def delete_profile(self, user_id: uuid.UUID):
        try:
            stmt = select(UsersOrm).where(UsersOrm.id == user_id)
            result = await self.db.session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                raise ObjectNotFoundException("User not found")
            user.role_id = 1
            await self.db.commit()
            return {"status": "OK"}
        except ObjectNotFoundHTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise InternalErrorHTTPException()

    async def become_psychologist(
        self, user_id: uuid.UUID, data: BecomePsychologistRequest
    ):
        try:
            stmt = (
                select(UsersOrm)
                .where(UsersOrm.id == user_id)
                .options(selectinload(UsersOrm.inquiries))
            )
            result = await self.db.session.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                raise ObjectNotFoundException("User not found")
            user.username = data.username
            user.birth_date = data.birth_date
            user.higher_education_university = data.higher_education_university
            user.higher_education_specialization = data.higher_education_specialization
            user.academic_degree = data.academic_degree
            user.courses = data.courses
            user.work_format = data.work_format
            user.association = data.association
            user.role_id = user.role_id
            if data.inquiry_ids is not None:
                stmt_inq = select(InquiryOrm).where(InquiryOrm.id.in_(data.inquiry_ids))
                result_inq = await self.db.session.execute(stmt_inq)
                new_inquiries = result_inq.scalars().all()
                user.inquiries = new_inquiries
            await self.db.commit()
            return {"status": "OK", "message": "Successfully became psychologist"}
        except ObjectNotFoundHTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            raise InternalErrorHTTPException()

    async def get_psychologist(self, psychologist_id: uuid.UUID):
        try:
            stmt = (
                select(UsersOrm)
                .where(UsersOrm.id == psychologist_id)
                .options(selectinload(UsersOrm.inquiries))
            )
            result = await self.db.session.execute(stmt)
            psychologist = result.scalar_one_or_none()
            if not psychologist:
                raise ObjectNotFoundException()
            if psychologist.role_id != 2:
                raise ObjectNotFoundException()
            return PsychologistResponseRequest.model_validate(psychologist)
        except ObjectNotFoundException as ex:
            raise ex
        except Exception as ex:
            logger.error(f"Ошибка при получении психологов: {ex}")
            raise MyAppException()

    async def get_all_psychologists(
        self,
        page: int = 1,
        per_page: int | None = None,
        inquiry_ids: Optional[List[int]] = None,
    ):
        try:
            stmt = (
                select(UsersOrm)
                .where(UsersOrm.role_id == 2)
                .options(selectinload(UsersOrm.inquiries))
            )
            if inquiry_ids:
                subq = (
                    select(user_inquiry.c.user_id)
                    .where(user_inquiry.c.inquiry_id.in_(inquiry_ids))
                    .group_by(user_inquiry.c.user_id)
                    .having(
                        func.count(user_inquiry.c.inquiry_id.distinct())
                        == len(inquiry_ids)
                    )
                    .subquery()
                )
                stmt = stmt.where(UsersOrm.id.in_(select(subq.c.user_id)))
            if per_page is not None:
                offset = (page - 1) * per_page
                stmt = stmt.offset(offset).limit(per_page)
            result = await self.db.session.execute(stmt)
            psychologists = result.scalars().all()
            total = 0
            if per_page is not None:
                count_stmt = (
                    select(func.count())
                    .select_from(UsersOrm)
                    .where(UsersOrm.role_id == 2)
                )
                total_result = await self.db.session.execute(count_stmt)
                total = total_result.scalar_one()
            return {
                "items": [
                    PsychologistResponseRequest.model_validate(p) for p in psychologists
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page
                if per_page and total
                else 1,
            }
        except ObjectNotFoundException as ex:
            raise ex
        except Exception as ex:
            logger.debug(str(ex))
            logger.error(f"Ошибка при получении психологов: {ex}")
            raise MyAppException()

    async def get_client_test_results(
        self, client_id: uuid.UUID, psychologist_id: uuid.UUID
    ) -> list[Dict[str, Any]]:
        try:
            relation = await self.db.clients.get_one_or_none(
                client_id=client_id, mentor_id=psychologist_id, status=True
            )
            if not relation:
                raise ObjectNotFoundException(
                    f"Клиент с ID {client_id} не найден или не является вашим подопечным"
                )
            test_results = await self.db.test_result.get_filtered(user_id=client_id)
            if not test_results:
                return []
            results = []
            for tr in test_results:
                try:
                    scale_results = await self.db.scale_result.get_filtered(
                        test_result_id=tr.id
                    )
                    result = {
                        "test_id": str(tr.test_id),
                        "test_result_id": str(tr.id),
                        "datetime": tr.date.isoformat(),
                        "scale_results": [],
                    }
                    for sr in scale_results:
                        try:
                            scale = await self.db.scales.get_one(id=sr.scale_id)
                            if not scale:
                                logger.warning(
                                    f"Шкала с ID {sr.scale_id} не найдена, пропускаем"
                                )
                                continue
                            borders = await self.db.borders.get_filtered(
                                scale_id=scale.id
                            )
                            conclusion = ""
                            color = ""
                            user_recommendation = ""
                            for border in borders:
                                if (
                                    border.left_border
                                    <= sr.score
                                    <= border.right_border
                                ):
                                    conclusion = border.title
                                    color = border.color
                                    user_recommendation = border.user_recommendation
                                    break
                            result["scale_results"].append(
                                {
                                    "scale_id": str(scale.id),
                                    "scale_title": scale.title,
                                    "score": sr.score,
                                    "max_score": scale.max,
                                    "conclusion": conclusion,
                                    "color": color,
                                    "user_recommendation": user_recommendation,
                                }
                            )
                        except Exception as e:
                            logger.error(
                                f"Ошибка обработки результата шкалы {sr.id}: {str(e)}"
                            )
                            continue
                    results.append(result)
                except Exception as e:
                    logger.error(f"Ошибка обработки результата теста {tr.id}: {str(e)}")
                    continue
            return results
        except ObjectNotFoundException:
            raise
        except Exception as ex:
            logger.error(
                f"Ошибка при получении результатов тестов клиента: {ex}", exc_info=True
            )
            raise MyAppException("Произошла ошибка при получении результатов тестов")

    async def get_short_client_test_results(
        self, client_id: uuid.UUID, psychologist_id: uuid.UUID
    ) -> list[Dict[str, Any]]:
        """
        По одной карточке на тест, с датой и ID последнего прохождения.
        """
        try:
            relation = await self.db.clients.get_one_or_none(
                client_id=client_id, mentor_id=psychologist_id, status=True
            )
            if not relation:
                raise ObjectNotFoundException(
                    f"Клиент с ID {client_id} не найден или не является вашим подопечным"
                )
            test_results = await self.db.test_result.get_filtered(user_id=client_id)
            if not test_results:
                return []
            latest_info: Dict[uuid.UUID, tuple[datetime, uuid.UUID]] = {}
            for tr in test_results:
                tid = tr.test_id
                if tid not in latest_info or tr.date > latest_info[tid][0]:
                    latest_info[tid] = (tr.date, tr.id)
            results = []
            for test_id, (last_date, last_result_id) in latest_info.items():
                test_info = await self.db.tests.get_one(id=test_id)
                if not test_info:
                    logger.warning(f"Тест с ID {test_id} не найден в базе, пропускаем")
                    continue
                results.append(
                    {
                        "test_id": str(test_id),
                        "test_name": test_info.title,
                        "short_desc": test_info.short_desc,
                        "last_date": last_date.isoformat(),
                        "test_result_id": str(last_result_id),
                    }
                )
            results.sort(key=lambda x: x["last_date"], reverse=True)
            return results
        except ObjectNotFoundException:
            raise
        except Exception as ex:
            logger.error(
                f"Ошибка при получении кратких результатов тестов клиента: {ex}",
                exc_info=True,
            )
            raise MyAppException("Произошла ошибка при получении результатов тестов")
