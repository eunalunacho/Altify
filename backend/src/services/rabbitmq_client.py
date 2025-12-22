import pika
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

# RabbitMQ 연결 설정
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "altify")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_DEFAULT_PASS", "altify2025")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "alt_generation_queue")
RABBITMQ_DLQ = os.getenv("RABBITMQ_DLQ", "alt_generation_dlq")
RABBITMQ_DLX = os.getenv("RABBITMQ_DLX", "alt_generation_dlx")

# 재시도 설정
MAX_RETRY_COUNT = int(os.getenv("MAX_RETRY_COUNT", "3"))


def get_rabbitmq_connection():
    """RabbitMQ 연결 생성"""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )
    return pika.BlockingConnection(parameters)


def setup_queues(channel):
    """
    RabbitMQ 큐 및 DLQ 설정
    
    Args:
        channel: RabbitMQ 채널
    """
    # DLX (Dead Letter Exchange) 선언
    channel.exchange_declare(
        exchange=RABBITMQ_DLX,
        exchange_type='direct',
        durable=True
    )
    
    # DLQ (Dead Letter Queue) 선언
    channel.queue_declare(
        queue=RABBITMQ_DLQ,
        durable=True
    )
    channel.queue_bind(
        exchange=RABBITMQ_DLX,
        queue=RABBITMQ_DLQ,
        routing_key=RABBITMQ_DLQ
    )
    
    # 메인 큐 선언 (DLX 연결)
    channel.queue_declare(
        queue=RABBITMQ_QUEUE,
        durable=True,
        arguments={
            'x-dead-letter-exchange': RABBITMQ_DLX,
            'x-dead-letter-routing-key': RABBITMQ_DLQ,
            'x-message-ttl': 3600000  # 1시간 후 DLQ로 이동 (선택사항)
        }
    )


def publish_task_id(task_id: int, queue_name: str = None, retry_count: int = 0, error_msg: Optional[str] = None):
    """
    RabbitMQ에 작업 ID 발행 (재시도 정보 포함)
    
    Args:
        task_id: 발행할 작업 ID
        queue_name: 큐 이름 (기본값: RABBITMQ_QUEUE 환경 변수)
        retry_count: 재시도 횟수 (기본값: 0)
        error_msg: 이전 오류 메시지 (있는 경우)
    
    Raises:
        Exception: 발행 실패 시
    """
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        # 큐 설정
        setup_queues(channel)
        
        # 큐 이름 결정
        target_queue = queue_name or RABBITMQ_QUEUE
        
        # 메시지 페이로드 구성 (메타데이터 포함)
        payload = {
            "task_id": task_id,
            "retry_count": retry_count,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "task_id": task_id
            }
        }
        
        if error_msg:
            payload["error_msg"] = error_msg
        
        message = json.dumps(payload)
        
        # 메시지 발행
        channel.basic_publish(
            exchange="",
            routing_key=target_queue,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # 메시지 영속성
                headers={
                    'x-retry-count': retry_count,
                    'x-task-id': str(task_id)
                }
            )
        )
        
        connection.close()
    except Exception as e:
        raise Exception(f"RabbitMQ 메시지 발행 실패: {e}")

