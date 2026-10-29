import datetime
from sqlalchemy.dialects.postgresql import UUID
from src.database import Base
from src.utils.encryption import EncryptedFloatType
import uuid
from sqlalchemy import ForeignKey, ARRAY, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List


class TestOrm(Base):
    __tablename__ = "test"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    type: Mapped[int] = mapped_column(nullable=True)
    title: Mapped[str]
    description: Mapped[str]
    short_desc: Mapped[str]
    link: Mapped[str]

    test_result: Mapped[List["TestResultOrm"]] = relationship(
        cascade="all, delete-orphan"
    )
    question: Mapped[List["QuestionOrm"]] = relationship(
        back_populates="test", cascade="all, delete-orphan"
    )
    scale: Mapped[List["ScaleOrm"]] = relationship(cascade="all, delete-orphan")


class TestResultOrm(Base):
    __tablename__ = "test_result"
    __table_args__ = (Index("ix_test_result_lookup", "user_id", "test_id", "date"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test.id", ondelete="CASCADE")
    )
    date: Mapped[datetime.datetime]

    scale_result: Mapped[List["ScaleResultOrm"]] = relationship(
        back_populates="test_result",
        cascade="all, delete-orphan",
        lazy="selectin",  # Используем selectin для асинхронной загрузки
    )


class ScaleOrm(Base):
    __tablename__ = "scale"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    title: Mapped[str]
    position: Mapped[int] = mapped_column(default=0, server_default="0")
    min: Mapped[int]
    max: Mapped[int]
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test.id", ondelete="CASCADE"), nullable=True
    )

    scale_result: Mapped[List["ScaleResultOrm"]] = relationship(
        cascade="all, delete-orphan"
    )
    borders: Mapped[List["BordersOrm"]] = relationship(
        back_populates="scale", cascade="all, delete-orphan"
    )


class ScaleResultOrm(Base):
    __tablename__ = "scale_result"
    __table_args__ = (Index("ix_scale_result_lookup", "test_result_id", "scale_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    score: Mapped[float] = mapped_column(EncryptedFloatType())
    scale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scale.id", ondelete="CASCADE")
    )
    test_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_result.id", ondelete="CASCADE")
    )

    test_result: Mapped["TestResultOrm"] = relationship(back_populates="scale_result")


class BordersOrm(Base):
    __tablename__ = "borders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    left_border: Mapped[float]
    right_border: Mapped[float]
    color: Mapped[str]
    title: Mapped[str]
    user_recommendation: Mapped[str] = mapped_column(nullable=True)
    scale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scale.id", ondelete="CASCADE")
    )

    scale: Mapped["ScaleOrm"] = relationship(back_populates="borders")


class QuestionOrm(Base):
    __tablename__ = "question"
    __table_args__ = (Index("ix_question_lookup", "test_id", "number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    text: Mapped[str]
    number: Mapped[int]
    opposite_text: Mapped[str] = mapped_column(nullable=True)
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test.id", ondelete="CASCADE")
    )

    # В PostgreSQL — массив UUID; JSON используется только в тестовой SQLite.
    answer_choice: Mapped[List[uuid.UUID]] = mapped_column(ARRAY(UUID), default=list)

    test: Mapped["TestOrm"] = relationship(back_populates="question")


class AnswerChoiceOrm(Base):
    __tablename__ = "answer_choice"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    text: Mapped[str]
    score: Mapped[int]
