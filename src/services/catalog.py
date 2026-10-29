"""Загрузка недостающих записей каталога без перезаписи существующих."""

import uuid
from src.utils.data import load_data
from src.models import (
    TestOrm,
    ScaleOrm,
    BordersOrm,
    AnswerChoiceOrm,
    QuestionOrm,
    InquiryOrm,
)


async def seed_catalog(db):
    catalog = [
        (TestOrm, "test_info", ("id",)),
        (ScaleOrm, "scale_info", ("id", "test_id")),
        (BordersOrm, "borders_info", ("id", "scale_id")),
        (AnswerChoiceOrm, "answer_choices_info", ("id",)),
        (QuestionOrm, "questions_info", ("id", "test_id")),
        (InquiryOrm, "inquiry", ()),
    ]
    created = 0
    for model, filename, uuid_fields in catalog:
        positions = {}
        for source in load_data(f"src/services/info/{filename}.json"):
            values = {
                key: value
                for key, value in source.items()
                if key in model.__table__.columns
            }
            for key in uuid_fields:
                if values.get(key):
                    values[key] = uuid.UUID(str(values[key]))
            if model is ScaleOrm:
                tid = values["test_id"]
                positions[tid] = positions.get(tid, 0) + 1
                values["position"] = positions[tid]
            if model is QuestionOrm:
                values["answer_choice"] = [
                    uuid.UUID(str(x)) for x in values["answer_choice"]
                ]
            if await db.session.get(model, values["id"]) is None:
                db.session.add(model(**values))
                created += 1
        await db.session.flush()
    await db.commit()
    return {"status": "OK", "created": created}
