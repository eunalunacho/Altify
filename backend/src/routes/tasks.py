from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from typing import Optional, List
import uuid
import io
import re
from bs4 import BeautifulSoup

from src.database import get_db
from src.models.task import Task, TaskStatus
from src.schemas.task import TaskResponse
from src.services.minio_client import get_minio_client, upload_image_to_minio, delete_image_from_minio
from src.services.rabbitmq_client import publish_task_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskApproveRequest(BaseModel):
    """Task 승인 요청 스키마"""
    final_alt: str
    is_approved: bool = True


def preprocess_text(text: str) -> str:
    """
    문맥 텍스트 전처리 함수
    
    - BeautifulSoup을 사용하여 HTML 태그 제거
    - 불필요한 공백 및 빈 줄 제거
    
    Args:
        text: 원본 텍스트
    
    Returns:
        전처리된 텍스트
    """
    # HTML 태그 제거
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text()
    
    # 여러 공백을 하나로 통합
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    # 앞뒤 공백 제거
    cleaned_text = cleaned_text.strip()
    
    # 빈 줄 제거 (여러 줄이 있는 경우)
    cleaned_text = re.sub(r'\n\s*\n', '\n', cleaned_text)
    
    return cleaned_text


@router.post("/upload", response_model=TaskResponse, status_code=202)
async def upload_task(
    이미지: UploadFile = File(...),
    문맥텍스트: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Task 업로드 엔드포인트
    
    트랜잭션 규칙:
    - MinIO에 이미지 저장과 DB에 Task 객체 저장이 모두 성공해야만 커밋
    - 둘 중 하나라도 실패하면 롤백하고 오류 응답 반환
    - 커밋 성공 후에만 RabbitMQ에 작업 ID 발행
    
    처리 순서:
    1. 문맥 텍스트 전처리
    2. DB에 Task 객체 생성 및 flush (커밋 전)
    3. MinIO에 이미지 업로드
    4. 둘 다 성공 시 DB 커밋
    5. 커밋 성공 후 RabbitMQ에 작업 ID 발행
    """
    minio_client = None
    task = None
    이미지경로 = None
    task_id = None
    
    try:
        # 1. 문맥 텍스트 전처리
        try:
            processed_text = preprocess_text(문맥텍스트)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"텍스트 전처리 실패: {str(e)}"
            )
        
        # 2. 파일 데이터 읽기 및 객체 이름 생성
        file_data = await 이미지.read()
        file_stream = io.BytesIO(file_data)
        file_extension = 이미지.filename.split('.')[-1] if '.' in 이미지.filename else 'jpg'
        object_name = f"{uuid.uuid4()}.{file_extension}"
        
        # 3. DB에 Task 객체 생성 및 flush (커밋 전)
        # image_path는 임시로 설정하고, MinIO 업로드 후 실제 경로로 업데이트
        try:
            task = Task(
                image_path="",  # 임시 값, MinIO 업로드 후 업데이트
                context_text=processed_text,
                status=TaskStatus.PENDING
            )
            db.add(task)
            db.flush()  # ID를 얻기 위해 flush (아직 커밋하지 않음)
            task_id = task.id
        except SQLAlchemyError as e:
            # DB 저장 실패 시 롤백
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"데이터베이스 저장 실패: {str(e)}"
            )
        
        # 4. MinIO에 이미지 업로드
        try:
            minio_client = get_minio_client()
            이미지경로 = upload_image_to_minio(
                minio_client,
                file_stream,
                object_name,
                bucket_name="alt-images"
            )
            # Task 객체의 image_path 업데이트
            task.image_path = 이미지경로
            db.flush()  # 변경사항 flush (아직 커밋하지 않음)
        except Exception as e:
            # MinIO 업로드 실패 시 DB 롤백
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"이미지 업로드 실패: {str(e)}"
            )
        
        # 5. 모든 작업이 성공했으므로 커밋
        try:
            db.commit()
        except SQLAlchemyError as e:
            # 커밋 실패 시 MinIO 파일 삭제 (보상 로직)
            if minio_client and 이미지경로:
                try:
                    delete_image_from_minio(minio_client, 이미지경로)
                except Exception as cleanup_error:
                    # MinIO 삭제 실패는 로그만 남김
                    print(f"Warning: 커밋 실패 후 MinIO 파일 삭제 실패 (image_path: {이미지경로}): {str(cleanup_error)}")
            
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"트랜잭션 커밋 실패: {str(e)}"
            )
        
        # 6. RabbitMQ에 작업 ID 발행 (커밋 성공 후에만 실행)
        try:
            publish_task_id(task_id, queue_name="alt_generation_queue")
        except Exception as e:
            # RabbitMQ 발행 실패는 로그만 남기고 응답은 성공으로 처리
            # (이미 DB와 MinIO는 성공했으므로)
            print(f"Warning: RabbitMQ 메시지 발행 실패 (task_id: {task_id}): {str(e)}")
        
        # 7. 응답 반환 (202 Accepted)
        return TaskResponse.model_validate(task)
        
    except HTTPException:
        # HTTPException은 그대로 전파
        raise
    except Exception as e:
        # 예상치 못한 오류 발생 시 정리 작업
        # MinIO 파일이 업로드되었지만 커밋이 실패한 경우 파일 삭제
        if minio_client and 이미지경로:
            try:
                delete_image_from_minio(minio_client, 이미지경로)
            except Exception as cleanup_error:
                print(f"Warning: 예외 발생 후 MinIO 파일 삭제 실패 (image_path: {이미지경로}): {str(cleanup_error)}")
        
        # DB 롤백
        try:
            db.rollback()
        except Exception:
            pass  # 이미 롤백되었거나 트랜잭션이 없는 경우
        
        raise HTTPException(
            status_code=500,
            detail=f"작업 업로드 중 오류 발생: {str(e)}"
        )


@router.post("/bulk-upload", response_model=List[TaskResponse], status_code=202)
async def bulk_upload_tasks(
    images: List[UploadFile] = File(...),
    contexts: List[str] = Form(...),
    db: Session = Depends(get_db)
):
    """
    여러 이미지-문맥 쌍을 한 번에 업로드하는 엔드포인트
    
    Args:
        images: 이미지 파일 리스트
        contexts: 문맥 텍스트 리스트 (images와 1:1 매핑)
        db: 데이터베이스 세션
    
    Returns:
        생성된 Task 리스트
    """
    if len(images) != len(contexts):
        raise HTTPException(
            status_code=400,
            detail="이미지와 문맥 텍스트의 개수가 일치하지 않습니다."
        )
    
    if len(images) == 0:
        raise HTTPException(
            status_code=400,
            detail="최소 하나의 이미지가 필요합니다."
        )
    
    created_tasks = []
    minio_client = None
    uploaded_paths = []
    
    try:
        minio_client = get_minio_client()
        
        # 각 이미지-문맥 쌍 처리
        for idx, (image, context_text) in enumerate(zip(images, contexts)):
            task = None
            image_path = None
            task_id = None
            
            try:
                # 1. 문맥 텍스트 전처리
                try:
                    processed_text = preprocess_text(context_text)
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"텍스트 전처리 실패 (인덱스 {idx}): {str(e)}"
                    )
                
                # 2. 파일 데이터 읽기 및 객체 이름 생성
                file_data = await image.read()
                file_stream = io.BytesIO(file_data)
                file_extension = image.filename.split('.')[-1] if '.' in image.filename else 'jpg'
                object_name = f"{uuid.uuid4()}.{file_extension}"
                
                # 3. DB에 Task 객체 생성 및 flush (커밋 전)
                try:
                    task = Task(
                        image_path="",  # 임시 값, MinIO 업로드 후 업데이트
                        context_text=processed_text,
                        status=TaskStatus.PENDING
                    )
                    db.add(task)
                    db.flush()  # ID를 얻기 위해 flush
                    task_id = task.id
                except SQLAlchemyError as e:
                    db.rollback()
                    raise HTTPException(
                        status_code=500,
                        detail=f"데이터베이스 저장 실패 (인덱스 {idx}): {str(e)}"
                    )
                
                # 4. MinIO에 이미지 업로드
                try:
                    image_path = upload_image_to_minio(
                        minio_client,
                        file_stream,
                        object_name,
                        bucket_name="alt-images"
                    )
                    task.image_path = image_path
                    uploaded_paths.append(image_path)
                    db.flush()  # 변경사항 flush
                except Exception as e:
                    db.rollback()
                    raise HTTPException(
                        status_code=500,
                        detail=f"이미지 업로드 실패 (인덱스 {idx}): {str(e)}"
                    )
                
                # 5. 커밋
                try:
                    db.commit()
                except SQLAlchemyError as e:
                    # 커밋 실패 시 MinIO 파일 삭제
                    if minio_client and image_path:
                        try:
                            delete_image_from_minio(minio_client, image_path)
                            uploaded_paths.remove(image_path)
                        except Exception:
                            pass
                    db.rollback()
                    raise HTTPException(
                        status_code=500,
                        detail=f"트랜잭션 커밋 실패 (인덱스 {idx}): {str(e)}"
                    )
                
                # 6. RabbitMQ에 작업 ID 발행
                try:
                    publish_task_id(task_id, queue_name="alt_generation_queue")
                except Exception as e:
                    print(f"Warning: RabbitMQ 메시지 발행 실패 (task_id: {task_id}): {str(e)}")
                
                created_tasks.append(TaskResponse.model_validate(task))
                
            except HTTPException:
                # HTTPException은 전파하고 이미 처리된 작업은 정리
                # 실패한 작업 이후의 작업들은 처리하지 않음
                raise
            except Exception as e:
                # 예상치 못한 오류
                if minio_client and image_path:
                    try:
                        delete_image_from_minio(minio_client, image_path)
                        if image_path in uploaded_paths:
                            uploaded_paths.remove(image_path)
                    except Exception:
                        pass
                
                try:
                    db.rollback()
                except Exception:
                    pass
                
                raise HTTPException(
                    status_code=500,
                    detail=f"작업 업로드 중 오류 발생 (인덱스 {idx}): {str(e)}"
                )
        
        return created_tasks
        
    except HTTPException:
        raise
    except Exception as e:
        # 전체 실패 시 정리 작업
        if minio_client:
            for path in uploaded_paths:
                try:
                    delete_image_from_minio(minio_client, path)
                except Exception:
                    pass
        
        try:
            db.rollback()
        except Exception:
            pass
        
        raise HTTPException(
            status_code=500,
            detail=f"대량 업로드 중 오류 발생: {str(e)}"
        )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """
    Task 조회 엔드포인트
    
    Args:
        task_id: Task ID
        db: 데이터베이스 세션
    
    Returns:
        Task 정보
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task를 찾을 수 없습니다.")
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}/approve", response_model=TaskResponse)
async def approve_task(
    task_id: int,
    request: TaskApproveRequest,
    db: Session = Depends(get_db)
):
    """
    Task ALT 텍스트 승인 엔드포인트
    
    Args:
        task_id: Task ID
        request: 승인 요청 데이터
        db: 데이터베이스 세션
    
    Returns:
        업데이트된 Task 정보
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task를 찾을 수 없습니다.")
    
    try:
        task.final_alt = request.final_alt
        task.is_approved = request.is_approved
        
        db.commit()
        db.refresh(task)
        
        return TaskResponse.model_validate(task)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"승인 저장 실패: {str(e)}"
        )
