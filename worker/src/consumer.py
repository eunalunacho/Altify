import aio_pika
import json
import asyncio
import logging
from typing import Optional
import os

from src.core.model import model_loader
from src.services.minio_handler import download_image_from_minio
from src.services.db_handler import (
    update_task_status,
    get_task,
    save_result
)
from src.models.task import TaskStatus

logger = logging.getLogger(__name__)

# RabbitMQ 연결 설정
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE")

if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")
if not RABBITMQ_QUEUE:
    raise RuntimeError("RABBITMQ_QUEUE is not set")



async def process_message(message: aio_pika.IncomingMessage):
    """
    RabbitMQ 메시지 처리 함수
    
    Args:
        message: 수신된 메시지

    """

    task_id = None
    try:
        async with message.process(requeue=False):
            # 1. 메시지 파싱 (Task ID 추출)
            body = message.body.decode()
            data = json.loads(body)
            task_id = data.get("task_id")
            
            if not task_id:
                logger.error("메시지에 task_id가 없습니다.")
                return
            
            logger.info(f"Task {task_id} 처리 시작")

            # 2. DB 상태 업데이트 (PROCESSING)
            ok = update_task_status(task_id, TaskStatus.PROCESSING)
            if not ok:
                raise RuntimeError(f"상태 업데이트 실패: task_id={task_id}")
            
            # 3. DB에서 Task 정보 조회
            task = get_task(task_id)
            if not task:
                raise RuntimeError(f"Task not found: task_id={task_id}")
            
            # 4. MinIO에서 이미지 다운로드
            try:
                image = download_image_from_minio(task.image_path)
            except Exception as e:
                update_task_status(task_id, TaskStatus.FAILED)
                raise RuntimeError(f"이미지 다운로드 실패: task_id={task_id}") from e

            
            # 5. 모델로 ALT 텍스트 2개 생성
            try:
                logger.info(f"Task {task_id} 추론 시작 (2개 ALT 생성)")
                alt_text1, alt_text2 = model_loader.generate_captions(
                    image=image,
                    context=task.context_text
                )
                logger.info(f"Task {task_id} 추론 완료 (ALT 2개 생성됨)")
            finally:
                try:
                    del image # image는 성공/실패 상관없이 해제
                except Exception:
                    pass
            
            # 6. DB에 결과 저장 및 상태 업데이트 (DONE)
            ok = save_result(task_id, alt_text1, alt_text2)
            if not ok:
                update_task_status(task_id, TaskStatus.FAILED)
                raise RuntimeError(f"결과 저장 실패: task_id={task_id}")
        
            
            logger.info(f"Task {task_id} 처리 완료")
            
            
            
    except json.JSONDecodeError as e:
        logger.error(f"메시지 파싱 실패: {str(e)}", exc_info=True)
    
    except Exception as e:
        logger.error(f"메시지 처리 중 예외 발생 (task_id: {task_id}): {str(e)}", exc_info=True)
        # 예외 발생 시 상태를 FAILED로 변경
        if task_id:
            try:
                update_task_status(task_id, TaskStatus.FAILED)
            except Exception:
                logger.error("FAILED 상태 업데이트도 실패 (task_id=%s)", task_id, exc_info=True)
            
            # 메시지를 DLQ로 이동 (requeue=False)


async def start_consumer():
    """RabbitMQ Consumer 시작"""
    logger.info("RabbitMQ 연결 시도: %s", RABBITMQ_URL)
    logger.info("구독 큐: %s", RABBITMQ_QUEUE)

    # RabbitMQ 연결
    
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        logger.info("RabbitMQ 연결 성공")
    except Exception as e:
        logger.error(f"RabbitMQ 연결 실패: {str(e)}")
        raise
    
    try:
        # 채널 생성
        channel = await connection.channel()
        
        # QoS 설정 (한 번에 하나의 메시지만 처리)
        await channel.set_qos(prefetch_count=1)
        
        # 큐 선언
        queue = await channel.declare_queue(
            RABBITMQ_QUEUE,
            durable=True,
            passive=True
        )
        
        logger.info(f"큐 '{RABBITMQ_QUEUE}' 구독 시작")
        
        # 메시지 수신 시작
        await queue.consume(process_message)
        
        logger.info("Consumer 실행 중... 메시지 대기 중...")
        
        # 무한 대기
        await asyncio.Future()  # 영원히 대기
        
    except Exception as e:
        logger.error(f"Consumer 실행 중 오류: {str(e)}")
        raise
    finally:
        await connection.close()

