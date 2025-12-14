from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class TaskStatus(str, enum.Enum):
    """Task 상태 Enum"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class Task(Base):
    """Task 테이블 모델"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    image_path = Column(String, nullable=False)
    context_text = Column(String, nullable=False)

    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)

    alt_generated_1 = Column(String, nullable=True)
    alt_generated_2 = Column(String, nullable=True)

    selected_alt_index = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    final_alt = Column(String, nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)