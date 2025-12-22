import aio_pika
import json
import asyncio
import logging
from typing import Optional
import os
import time
from datetime import datetime

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
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "alt_generation_queue")
RABBITMQ_DLQ = os.getenv("RABBITMQ_DLQ", "alt_generation_dlq")
RABBITMQ_DLX = os.getenv("RABBITMQ_DLX", "alt_generation_dlx")
MAX_RETRY_COUNT = int(os.getenv("MAX_RETRY_COUNT", "3"))

if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL is not set")



def should_retry(retry_count: int, error: Exception) -> bool:
    """
    재시도 여부 결정
    
    Args:
        retry_count: 현재 재시도 횟수
        error: 발생한 오류
    
    Returns:
        재시도 여부
    """
    # 최대 재시도 횟수 초과 시 재시도 안 함
    if retry_count >= MAX_RETRY_COUNT:
        return False
    
    # GPU OOM 등 치명적 오류는 재시도 안 함 (즉시 DLQ로)
    if isinstance(error, RuntimeError) and "GPU 메모리 부족" in str(error):
        return False
    
    # 데이터 불일치 오류는 재시도 안 함
    if isinstance(error, RuntimeError) and ("Task not found" in str(error) or "이미지 다운로드 실패" in str(error)):
        return False
    
    # 그 외 오류는 재시도
    return True


async def process_message(message: aio_pika.IncomingMessage):
    """
    RabbitMQ 메시지 처리 함수 (재시도 및 DLQ 처리 포함)
    
    Args:
        message: 수신된 메시지
    """
    task_id = None
    retry_count = 0
    error_msg = None
    
    try:
        # 메시지 헤더에서 재시도 횟수 추출
        headers = message.headers or {}
        retry_count = headers.get('x-retry-count', 0)
        
        async with message.process(requeue=False):
            # 1. 메시지 파싱 (Task ID 및 메타데이터 추출)
            body = message.body.decode()
            data = json.loads(body)
            
            # 메시지 형식이 새로운 형식인지 확인
            if isinstance(data, dict) and "payload" in data:
                task_id = data.get("task_id") or data["payload"].get("task_id")
                retry_count = data.get("retry_count", retry_count)
                error_msg = data.get("error_msg")
            else:
                # 기존 형식 호환성 유지
                task_id = data.get("task_id")
            
            if not task_id:
                logger.error("메시지에 task_id가 없습니다.")
                return
            
            # 전체 처리 시간 측정 시작
            total_start = time.time()
            logger.info(f"Task {task_id} 처리 시작 (재시도 횟수: {retry_count})")

            # 2. DB 상태 업데이트 (PROCESSING)
            step_start = time.time()
            ok = update_task_status(task_id, TaskStatus.PROCESSING)
            db_update_time = time.time() - step_start
            if not ok:
                raise RuntimeError(f"상태 업데이트 실패: task_id={task_id}")
            logger.info(f"Task {task_id} [TIMING] DB 상태 업데이트: {db_update_time:.3f}s")
            
            # 3. DB에서 Task 정보 조회
            step_start = time.time()
            task = get_task(task_id)
            db_query_time = time.time() - step_start
            if not task:
                raise RuntimeError(f"Task not found: task_id={task_id} (데이터 불일치)")
            logger.info(f"Task {task_id} [TIMING] DB 조회: {db_query_time:.3f}s")
            
            # 4. MinIO에서 이미지 다운로드
            step_start = time.time()
            try:
                image = download_image_from_minio(task.image_path)
                minio_time = time.time() - step_start
                logger.info(f"Task {task_id} [TIMING] MinIO 다운로드: {minio_time:.3f}s")
            except Exception as e:
                minio_time = time.time() - step_start
                logger.error(f"Task {task_id} [TIMING] MinIO 다운로드 실패: {minio_time:.3f}s")
                error_msg = f"이미지 다운로드 실패: {str(e)}"
                update_task_status(task_id, TaskStatus.FAILED)
                raise RuntimeError(f"이미지 다운로드 실패: task_id={task_id}") from e

            
            # 5. 모델로 ALT 텍스트 2개 생성
            step_start = time.time()
            try:
                logger.info(f"Task {task_id} 추론 시작 (2개 ALT 생성)")
                alt_text1, alt_text2 = model_loader.generate_captions(
                    image=image,
                    context=task.context_text
                )
                inference_time = time.time() - step_start
                logger.info(f"Task {task_id} 추론 완료 (ALT 2개 생성됨) [TIMING] 추론: {inference_time:.3f}s")
            except RuntimeError as e:
                inference_time = time.time() - step_start
                logger.error(f"Task {task_id} [TIMING] 모델 추론 실패: {inference_time:.3f}s")
                # GPU OOM 등 치명적 오류
                error_msg = f"모델 추론 실패: {str(e)}"
                update_task_status(task_id, TaskStatus.FAILED)
                raise
            except Exception as e:
                inference_time = time.time() - step_start
                logger.error(f"Task {task_id} [TIMING] 모델 추론 중 예외: {inference_time:.3f}s")
                error_msg = f"모델 추론 중 예외 발생: {str(e)}"
                update_task_status(task_id, TaskStatus.FAILED)
                raise
            finally:
                try:
                    del image  # image는 성공/실패 상관없이 해제
                except Exception:
                    pass
            
            # 6. DB에 결과 저장 및 상태 업데이트 (DONE)
            step_start = time.time()
            ok = save_result(task_id, alt_text1, alt_text2)
            save_time = time.time() - step_start
            if not ok:
                logger.error(f"Task {task_id} [TIMING] 결과 저장 실패: {save_time:.3f}s")
                error_msg = "결과 저장 실패"
                update_task_status(task_id, TaskStatus.FAILED)
                raise RuntimeError(f"결과 저장 실패: task_id={task_id}")
            logger.info(f"Task {task_id} [TIMING] 결과 저장: {save_time:.3f}s")
        
            # 전체 처리 완료 시간
            total_time = time.time() - total_start
            logger.info(
                f"Task {task_id} 처리 완료 [TIMING] 전체: {total_time:.3f}s "
                f"(DB업데이트: {db_update_time:.3f}s, DB조회: {db_query_time:.3f}s, "
                f"MinIO: {minio_time:.3f}s, 추론: {inference_time:.3f}s, 저장: {save_time:.3f}s)"
            )
            
    except json.JSONDecodeError as e:
        logger.error(f"메시지 파싱 실패: {str(e)}", exc_info=True)
        # 파싱 실패는 재시도 안 함 (DLQ로)
        await send_to_dlq(message, task_id, retry_count, f"메시지 파싱 실패: {str(e)}")
    
    except Exception as e:
        logger.error(f"메시지 처리 중 예외 발생 (task_id: {task_id}, 재시도: {retry_count}): {str(e)}", exc_info=True)
        
        # 재시도 여부 결정
        if should_retry(retry_count, e):
            # 재시도: 메시지를 다시 큐에 발행
            await retry_message(task_id, retry_count + 1, error_msg or str(e))
            logger.info(f"Task {task_id} 재시도 예약 (재시도 횟수: {retry_count + 1})")
        else:
            # 재시도 한계 초과 또는 치명적 오류: DLQ로 이동
            await send_to_dlq(message, task_id, retry_count, error_msg or str(e))
            logger.error(f"Task {task_id} DLQ로 이동 (재시도 횟수: {retry_count}, 오류: {error_msg or str(e)})")
            
            # 상태를 FAILED로 변경
            if task_id:
                try:
                    update_task_status(task_id, TaskStatus.FAILED)
                except Exception:
                    logger.error("FAILED 상태 업데이트도 실패 (task_id=%s)", task_id, exc_info=True)


async def retry_message(task_id: int, retry_count: int, error_msg: str):
    """
    메시지를 재시도하기 위해 다시 큐에 발행
    
    Args:
        task_id: Task ID
        retry_count: 재시도 횟수
        error_msg: 오류 메시지
    """
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        payload = {
            "task_id": task_id,
            "retry_count": retry_count,
            "timestamp": datetime.utcnow().isoformat(),
            "error_msg": error_msg,
            "payload": {
                "task_id": task_id
            }
        }
        
        message_body = json.dumps(payload)
        
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=message_body.encode(),
                headers={'x-retry-count': retry_count, 'x-task-id': str(task_id)},
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=RABBITMQ_QUEUE
        )
        
        await connection.close()
    except Exception as e:
        logger.error(f"재시도 메시지 발행 실패 (task_id: {task_id}): {str(e)}", exc_info=True)


async def send_to_dlq(message: aio_pika.IncomingMessage, task_id: Optional[int], retry_count: int, error_msg: str):
    """
    메시지를 DLQ로 전송
    
    Args:
        message: 원본 메시지
        task_id: Task ID
        retry_count: 재시도 횟수
        error_msg: 오류 메시지
    """
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        # DLX 및 DLQ 선언
        dlx = await channel.declare_exchange(RABBITMQ_DLX, aio_pika.ExchangeType.DIRECT, durable=True)
        dlq = await channel.declare_queue(RABBITMQ_DLQ, durable=True)
        await dlq.bind(dlx, routing_key=RABBITMQ_DLQ)
        
        # DLQ 메시지 페이로드 구성
        dlq_payload = {
            "task_id": task_id,
            "retry_count": retry_count,
            "error_msg": error_msg,
            "timestamp": datetime.utcnow().isoformat(),
            "original_payload": message.body.decode() if message.body else None
        }
        
        dlq_message_body = json.dumps(dlq_payload)
        
        await dlx.publish(
            aio_pika.Message(
                body=dlq_message_body.encode(),
                headers={
                    'x-retry-count': retry_count,
                    'x-task-id': str(task_id) if task_id else 'unknown',
                    'x-error-msg': error_msg[:200]  # 헤더는 길이 제한이 있음
                },
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=RABBITMQ_DLQ
        )
        
        await connection.close()
        logger.info(f"메시지가 DLQ로 전송됨 (task_id: {task_id}, 재시도: {retry_count})")
    except Exception as e:
        logger.error(f"DLQ 전송 실패 (task_id: {task_id}): {str(e)}", exc_info=True)


async def start_consumer():
    """RabbitMQ Consumer 시작"""
    logger.info("RabbitMQ 연결 시도: %s", RABBITMQ_URL)
    logger.info("구독 큐: %s", RABBITMQ_QUEUE)
    logger.info("DLQ: %s", RABBITMQ_DLQ)
    logger.info("최대 재시도 횟수: %d", MAX_RETRY_COUNT)

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
        
        # DLX 및 DLQ 선언
        dlx = await channel.declare_exchange(
            RABBITMQ_DLX,
            aio_pika.ExchangeType.DIRECT,
            durable=True
        )
        dlq = await channel.declare_queue(RABBITMQ_DLQ, durable=True)
        await dlq.bind(dlx, routing_key=RABBITMQ_DLQ)
        logger.info(f"DLQ 설정 완료: {RABBITMQ_DLQ}")
        
        # 메인 큐 선언 (DLX 연결)
        queue = await channel.declare_queue(
            RABBITMQ_QUEUE,
            durable=True,
            arguments={
                'x-dead-letter-exchange': RABBITMQ_DLX,
                'x-dead-letter-routing-key': RABBITMQ_DLQ,
                'x-message-ttl': 3600000  # 백엔드와 동일하게 추가
            }
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

