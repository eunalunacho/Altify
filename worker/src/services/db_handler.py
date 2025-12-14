from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import os
import logging

from src.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

# 환경 변수에서 데이터베이스 URL 가져오기
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:{os.getenv('POSTGRES_PASSWORD', 'postgres')}@{os.getenv('POSTGRES_HOST', 'postgres')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB', 'altify')}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Session:
    """데이터베이스 세션 생성"""
    return SessionLocal()


def update_task_status(task_id: int, status: TaskStatus) -> bool:
    """
    Task 상태 업데이트
    
    Args:
        task_id: Task ID
        status: 새로운 상태 (TaskStatus enum)
    
    Returns:
        성공 여부
    """
    db = get_db_session()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error(f"Task를 찾을 수 없습니다: {task_id}")
            return False
        
        task.status = status
        
        # 상태가 DONE 또는 FAILED인 경우 finished_at 업데이트
        if status in [TaskStatus.DONE, TaskStatus.FAILED]:
            task.finished_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Task {task_id} 상태 업데이트: {status.value}")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"상태 업데이트 실패 (task_id: {task_id}): {str(e)}")
        return False
    finally:
        db.close()


def get_task(task_id: int) -> Task:
    """
    Task 조회
    
    Args:
        task_id: Task ID
    
    Returns:
        Task 객체 또는 None
    """
    db = get_db_session()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        return task
    except SQLAlchemyError as e:
        logger.error(f"Task 조회 실패 (task_id: {task_id}): {str(e)}")
        return None
    finally:
        db.close()


def save_result(task_id: int, alt_text: str, alt_text2: str = None) -> bool:
    """
    생성된 ALT 텍스트를 Task에 저장
    
    Args:
        task_id: Task ID
        alt_text: 첫 번째 생성된 ALT 텍스트
        alt_text2: 두 번째 생성된 ALT 텍스트 (선택사항)
    
    Returns:
        성공 여부
    """
    db = get_db_session()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error(f"Task를 찾을 수 없습니다: {task_id}")
            return False
        
        task.alt_generated_1 = alt_text
        if alt_text2:
            task.alt_generated_2 = alt_text2
        task.status = TaskStatus.DONE
        task.finished_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Task {task_id} 결과 저장 완료 (ALT 2개)")
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"결과 저장 실패 (task_id: {task_id}): {str(e)}")
        return False
    finally:
        db.close()

