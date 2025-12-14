import pika
import json
import os
from typing import Dict, Any

# RabbitMQ 연결 설정
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "altify")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_DEFAULT_PASS", "altify2025")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "alt_generation_queue")


def get_rabbitmq_connection():
    """RabbitMQ 연결 생성"""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )
    return pika.BlockingConnection(parameters)


def publish_task_id(task_id: int, queue_name: str = None):
    """
    RabbitMQ에 작업 ID 발행
    
    Args:
        task_id: 발행할 작업 ID
        queue_name: 큐 이름 (기본값: RABBITMQ_QUEUE 환경 변수 또는 "task_queue")
    
    Raises:
        Exception: 발행 실패 시
    """
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        # 큐 이름 결정
        target_queue = queue_name or RABBITMQ_QUEUE
        
        # 큐 선언 (존재하지 않으면 생성)
        channel.queue_declare(queue=target_queue, durable=True)
        
        # 메시지 발행
        message = json.dumps({"task_id": task_id})
        channel.basic_publish(
            exchange="",
            routing_key=target_queue,
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # 메시지 영속성
            )
        )
        
        connection.close()
    except Exception as e:
        raise Exception(f"RabbitMQ 메시지 발행 실패: {e}")

