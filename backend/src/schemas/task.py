from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from models.task import TaskStatus


class TaskCreate(BaseModel):
    """Task 생성 입력 스키마"""
    image_path: str
    context_text: str

    class Config:
        from_attributes = True
        use_enum_values = True


class TaskResponse(BaseModel):
    """Task 응답 스키마"""
    id: int
    image_path: str
    context_text: str
    status: TaskStatus
    alt_generated_1: Optional[str] = None
    alt_generated_2: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None
    final_alt: Optional[str] = None
    is_approved: bool

    class Config:
        from_attributes = True
        use_enum_values = True

