from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid
import io
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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
    selected_alt_index: Optional[int] = None  # 선택된 ALT 인덱스 (1 또는 2)

class TaskFinalizeItem(BaseModel):
    """여러 Task를 한 번에 확정할 때 사용하는 스키마"""
    task_id: int
    selected_alt_index: int
    final_alt: str

def extract_keywords(text: str, max_keywords: int = 10) -> str:
    """
    텍스트에서 핵심 키워드만 추출하는 함수
    
    - 한국어 명사, 영어 단어, 숫자 등을 추출
    - 불필요한 조사, 접속사, 감탄사 등은 제거
    - 최대 max_keywords 개의 키워드만 반환
    
    Args:
        text: 원본 텍스트
        max_keywords: 최대 키워드 개수
    
    Returns:
        추출된 키워드들을 공백으로 구분한 문자열
    """
    # 원본 텍스트 로깅 (너무 길면 잘라서)
    original_preview = text[:200] + "..." if len(text) > 200 else text
    logger.info(f"[키워드 추출 시작] 원본 텍스트 (일부): {original_preview}")
    
    # HTML 태그 제거
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text()
    logger.debug(f"[키워드 추출] HTML 태그 제거 후: {cleaned_text[:200] if len(cleaned_text) > 200 else cleaned_text}")
    
    # 특수문자 제거 (한글, 영문, 숫자, 공백만 남김)
    cleaned_text = re.sub(r'[^\w\s가-힣]', ' ', cleaned_text)
    
    # 여러 공백을 하나로 통합
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    logger.debug(f"[키워드 추출] 특수문자 제거 후: {cleaned_text[:200] if len(cleaned_text) > 200 else cleaned_text}")
    
    # 단어 분리
    words = cleaned_text.split()
    logger.info(f"[키워드 추출] 분리된 단어 개수: {len(words)}개")
    logger.debug(f"[키워드 추출] 분리된 단어 목록: {words}")
    
    # 불필요한 단어 필터링 (조사, 접속사, 감탄사 등)
    stop_words = {
        '은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로',
        '와', '과', '도', '만', '부터', '까지', '에게', '한테', '께',
        '그', '그것', '이것', '저것', '그런', '이런', '저런',
        '그리고', '또한', '또', '또는', '그러나', '하지만', '그런데',
        '아', '어', '오', '우', '으', '음', '응', '그래', '아니',
        '있다', '없다', '되다', '하다', '이다', '되다', '하다',
        'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
        'this', 'that', 'these', 'those', 'it', 'they', 'we', 'you'
    }
    
    # 키워드 추출 (2글자 이상인 단어, stop_words 제외)
    keywords = []
    seen = set()
    filtered_words = []  # 필터링된 단어들 추적
    
    for word in words:
        word_lower = word.lower().strip()
        # 필터링 조건 확인
        is_too_short = len(word) < 2
        is_stop_word = word_lower in stop_words
        is_duplicate = word_lower in seen
        is_digit = word_lower.isdigit()
        
        # 필터링된 단어 추적
        if is_too_short:
            filtered_words.append(f"{word}(1글자)")
        elif is_stop_word:
            filtered_words.append(f"{word}(stop_word)")
        elif is_duplicate:
            filtered_words.append(f"{word}(중복)")
        elif is_digit:
            filtered_words.append(f"{word}(숫자)")
        
        # 2글자 이상이고, stop_words에 없고, 이미 추가하지 않은 경우
        if (len(word) >= 2 and 
            word_lower not in stop_words and 
            word_lower not in seen and
            not word_lower.isdigit()):  # 순수 숫자는 제외
            keywords.append(word)
            seen.add(word_lower)
            logger.debug(f"[키워드 추출] 키워드 추가: '{word}' (누적: {len(keywords)}/{max_keywords})")
            
            # 최대 개수 도달 시 중단
            if len(keywords) >= max_keywords:
                logger.info(f"[키워드 추출] 최대 키워드 개수({max_keywords}) 도달, 추출 중단")
                break
    
    # 필터링된 단어들 로깅
    if filtered_words:
        logger.debug(f"[키워드 추출] 필터링된 단어들: {filtered_words[:20]}{'...' if len(filtered_words) > 20 else ''}")
    
    # 키워드가 없으면 빈 문자열 반환 (원본 문장 전체를 반환하지 않음)
    # 이렇게 하면 모델은 이미지만 보고 ALT를 생성하게 됨
    if not keywords:
        logger.warning(f"[키워드 추출 실패] 원본 텍스트에서 키워드를 찾을 수 없습니다. 빈 문자열을 반환합니다.")
        logger.warning(f"[키워드 추출 실패] 원본 텍스트: {text[:500]}")
        logger.warning(f"[키워드 추출 실패] 분리된 단어: {words}")
        logger.warning(f"[키워드 추출 실패] 필터링된 단어: {filtered_words}")
        return ""
    
    keywords_str = ' '.join(keywords)
    logger.info(f"[키워드 추출 완료] 원본 텍스트 길이: {len(text)}자")
    logger.info(f"[키워드 추출 완료] 분리된 단어 개수: {len(words)}개")
    logger.info(f"[키워드 추출 완료] 필터링된 단어 개수: {len(filtered_words)}개")
    logger.info(f"[키워드 추출 완료] 최종 추출된 키워드 개수: {len(keywords)}개")
    logger.info(f"[키워드 추출 완료] 추출된 키워드 목록: {keywords}")
    logger.info(f"[키워드 추출 완료] 최종 키워드 문자열: '{keywords_str}'")
    return keywords_str


def preprocess_text(text: str) -> str:
    """
    문맥 텍스트 전처리 함수
    
    - BeautifulSoup을 사용하여 HTML 태그 제거
    - 불필요한 공백 및 빈 줄 제거
    - 원본 텍스트를 그대로 반환 (키워드 추출 기능은 주석처리)
    
    Args:
        text: 원본 텍스트
    
    Returns:
        전처리된 텍스트 (원본 텍스트 그대로)
    """
    # HTML 태그 제거만 수행
    soup = BeautifulSoup(text, "html.parser")
    cleaned_text = soup.get_text()
    
    # 불필요한 공백 정리
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    
    # 키워드 추출 기능은 주석처리 - 원본 텍스트 그대로 사용
    # keywords = extract_keywords(text, max_keywords=10)
    # return keywords
    
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
        # Transactional Outbox Pattern 변형:
        # - DB 커밋은 성공했지만 RabbitMQ 발행 실패 시 롤백하지 않음
        # - Task는 PENDING 상태로 남아있으며, 별도 프로세스에서 재시도 가능
        try:
            publish_task_id(task_id, queue_name="alt_generation_queue")
            logger.info(f"RabbitMQ 메시지 발행 성공 (task_id: {task_id})")
        except Exception as e:
            # RabbitMQ 발행 실패 시:
            # - DB는 이미 커밋되었으므로 롤백하지 않음
            # - Task는 PENDING 상태로 유지됨
            # - 에러 로그만 남기고 응답은 성공으로 처리
            # - 별도 모니터링/재시도 프로세스에서 처리 가능
            logger.warning(
                f"RabbitMQ 메시지 발행 실패 (task_id: {task_id}): {str(e)}. "
                f"Task는 PENDING 상태로 유지되며, 별도 프로세스에서 재시도 가능합니다."
            )
        
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
                # Transactional Outbox Pattern 변형: 발행 실패 시 롤백하지 않음
                try:
                    publish_task_id(task_id, queue_name="alt_generation_queue")
                    logger.info(f"RabbitMQ 메시지 발행 성공 (task_id: {task_id})")
                except Exception as e:
                    logger.warning(
                        f"RabbitMQ 메시지 발행 실패 (task_id: {task_id}): {str(e)}. "
                        f"Task는 PENDING 상태로 유지됩니다."
                    )
                
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

@router.post("/finalize", response_model=List[TaskResponse])
async def finalize_tasks(
    requests: List[TaskFinalizeItem],
    db: Session = Depends(get_db)
):
    """
    여러 Task의 최종 ALT 선택 및 저장
    
    사용자가 선택하지 않은 경우 기본적으로 1번 문장이 이미 선택되어 있음.
    이 엔드포인트는 사용자가 명시적으로 다른 선택을 할 때 사용.
    """

    if not requests:
        raise HTTPException(status_code=400, detail="최소 하나의 작업이 필요합니다.")

    task_ids = [item.task_id for item in requests]
    tasks = db.query(Task).filter(Task.id.in_(task_ids)).all()
    task_map = {task.id: task for task in tasks}

    # 유효성 검사
    for item in requests:
        if item.selected_alt_index not in (1, 2):
            raise HTTPException(status_code=400, detail="선택된 ALT 번호는 1 또는 2여야 합니다.")

        task = task_map.get(item.task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {item.task_id}를 찾을 수 없습니다.")

        if task.status != TaskStatus.DONE:
            raise HTTPException(
                status_code=400,
                detail=f"ALT 생성이 완료된 작업만 확정할 수 있습니다. (task_id: {item.task_id})"
            )
        
        # 선택한 ALT 인덱스에 해당하는 텍스트가 있는지 확인
        if item.selected_alt_index == 1 and not task.alt_generated_1:
            raise HTTPException(
                status_code=400,
                detail=f"Task {item.task_id}에 1번 ALT 텍스트가 없습니다."
            )
        if item.selected_alt_index == 2 and not task.alt_generated_2:
            raise HTTPException(
                status_code=400,
                detail=f"Task {item.task_id}에 2번 ALT 텍스트가 없습니다."
            )

    try:
        for item in requests:
            task = task_map[item.task_id]
            
            # 선택한 인덱스에 맞는 ALT 텍스트 사용
            if item.selected_alt_index == 1:
                selected_alt = task.alt_generated_1
            else:
                selected_alt = task.alt_generated_2
            
            # 사용자가 제공한 final_alt가 있으면 사용, 없으면 선택한 ALT 사용
            task.final_alt = item.final_alt.strip() if item.final_alt.strip() else selected_alt
            task.selected_alt_index = item.selected_alt_index
            task.is_approved = True

            if not task.finished_at:
                task.finished_at = datetime.utcnow()

        db.commit()

        for task in task_map.values():
            db.refresh(task)

        return [TaskResponse.model_validate(task_map[item.task_id]) for item in requests]
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"작업 확정 저장 실패: {str(e)}")


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
        
        # selected_alt_index가 제공된 경우 설정
        if request.selected_alt_index is not None:
            if request.selected_alt_index not in (1, 2):
                raise HTTPException(
                    status_code=400,
                    detail="selected_alt_index는 1 또는 2여야 합니다."
                )
            task.selected_alt_index = request.selected_alt_index
        else:
            # 제공되지 않은 경우 기본값으로 1 설정
            task.selected_alt_index = 1
        
        if not task.finished_at:
            task.finished_at = datetime.utcnow()
        
        db.commit()
        db.refresh(task)
        
        return TaskResponse.model_validate(task)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"승인 저장 실패: {str(e)}"
        )
