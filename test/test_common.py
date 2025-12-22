# test/test_common.py
"""테스트 공통 유틸리티 함수"""
import os
import time
import json
import requests
import pika
from typing import Optional, List, Dict, Any
from pathlib import Path

# 테스트 설정
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_DEFAULT_USER", "altify")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_DEFAULT_PASS", "altify2025")
RABBITMQ_API_URL = os.getenv("RABBITMQ_API_URL", "http://localhost:15672/api")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "alt_generation_queue")
RABBITMQ_DLQ = os.getenv("RABBITMQ_DLQ", "alt_generation_dlq")

# 테스트 이미지 경로 (테스트용 작은 이미지)
TEST_IMAGE_PATH = Path(__file__).parent / "test_image.jpg"
TEST_CONTEXT = "친환경 소재로 만든 가방을 들고 있는 여성"


def create_test_image_file():
    """테스트용 더미 이미지 파일 생성 (실제 파일이 없을 경우 또는 1x1 픽셀인 경우 재생성)"""
    from PIL import Image
    
    # 파일이 없거나 크기가 잘못된 경우 재생성
    should_create = False
    if not TEST_IMAGE_PATH.exists():
        should_create = True
    else:
        # 기존 파일의 크기 확인 (1x1이면 재생성)
        try:
            with Image.open(TEST_IMAGE_PATH) as img:
                width, height = img.size
                if width == 1 and height == 1:
                    should_create = True
        except Exception:
            # 이미지 파일이 손상되었거나 읽을 수 없는 경우
            should_create = True
    
    if should_create:
        # LLaVA/CLIP 모델은 최소 224x224 크기를 요구하므로 224x224로 생성
        img = Image.new('RGB', (224, 224), color='red')
        img.save(TEST_IMAGE_PATH, 'JPEG')
        print(f"✓ Test image created: {TEST_IMAGE_PATH} (224x224)")
    
    return TEST_IMAGE_PATH


def upload_task(image_path: Optional[Path] = None, context: str = TEST_CONTEXT) -> Dict[str, Any]:
    """
    단일 작업 업로드 헬퍼 함수
    
    Returns:
        {'id': task_id, 'status': status_code, 'response': response_obj}
    """
    if image_path is None:
        image_path = create_test_image_file()
    
    with open(image_path, 'rb') as f:
        files = {'이미지': (image_path.name, f, 'image/jpeg')}
        data = {'문맥텍스트': context}
        
        response = requests.post(
            f"{API_BASE_URL}/tasks/upload",
            files=files,
            data=data,
            timeout=30
        )
        
        if response.status_code == 202:
            return {
                'id': response.json()['id'],
                'status': response.status_code,
                'response': response.json()
            }
        else:
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")


def upload_bulk_tasks(count: int, contexts: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    여러 작업 일괄 업로드 헬퍼 함수
    
    FastAPI는 같은 이름의 필드를 여러 번 보내면 리스트로 받을 수 있습니다.
    """
    image_path = create_test_image_file()
    
    files = []
    data = []
    
    for i in range(count):
        context = contexts[i] if contexts and i < len(contexts) else f"{TEST_CONTEXT} #{i+1}"
        # 같은 이름 'images'로 여러 파일 추가
        with open(image_path, 'rb') as f:
            files.append(('images', (image_path.name, f.read(), 'image/jpeg')))
        # 같은 이름 'contexts'로 여러 값 추가
        data.append(('contexts', context))
    
    # FormData로 전송 (files와 data 모두 사용)
    response = requests.post(
        f"{API_BASE_URL}/tasks/bulk-upload",
        files=files,
        data=data,
        timeout=60
    )
    
    if response.status_code == 202:
        tasks = response.json()
        return [{'id': t['id'], 'response': t} for t in tasks]
    else:
        raise Exception(f"Bulk upload failed: {response.status_code} - {response.text}")


def wait_for_task_completion(task_id: int, timeout: int = 300, poll_interval: float = 1.0) -> Dict[str, Any]:
    """
    작업이 완료될 때까지 대기
    
    Args:
        task_id: Task ID
        timeout: 최대 대기 시간 (초)
        poll_interval: 폴링 간격 (초)
    
    Returns:
        Task 정보 dict
    """
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = requests.get(f"{API_BASE_URL}/tasks/{task_id}")
        
        if response.status_code == 200:
            task = response.json()
            if task['status'] in ['DONE', 'FAILED']:
                return task
        
        time.sleep(poll_interval)
    
    raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")


def get_task(task_id: int) -> Dict[str, Any]:
    """작업 조회"""
    response = requests.get(f"{API_BASE_URL}/tasks/{task_id}")
    response.raise_for_status()
    return response.json()


def check_rabbitmq_queue_length(queue_name: str = RABBITMQ_QUEUE) -> int:
    """RabbitMQ 큐 길이 조회 (Management API 사용)"""
    try:
        auth = (RABBITMQ_USER, RABBITMQ_PASSWORD)
        # URL 인코딩: '/' -> '%2F'
        queue_name_encoded = queue_name.replace('/', '%2F')
        url = f"{RABBITMQ_API_URL}/queues/%2F/{queue_name_encoded}"
        
        response = requests.get(url, auth=auth, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('messages', 0)
        return 0
    except Exception as e:
        print(f"Warning: Failed to check queue length: {e}")
        return 0


def get_rabbitmq_connection():
    """RabbitMQ 연결 생성 (테스트용)"""
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )
    return pika.BlockingConnection(parameters)


def check_dlq_messages() -> List[Dict[str, Any]]:
    """DLQ에서 메시지 조회 (소비하지 않음)"""
    messages = []
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        # 메시지를 소비하지 않고 조회만 (auto_ack=False로 다시 넣음)
        method, properties, body = channel.basic_get(queue=RABBITMQ_DLQ, auto_ack=False)
        
        while method:
            try:
                msg_data = json.loads(body.decode())
                messages.append(msg_data)
                # 메시지를 다시 큐에 넣기 위해 nack
                channel.basic_nack(method.delivery_tag, requeue=True)
            except json.JSONDecodeError:
                pass
            
            method, properties, body = channel.basic_get(queue=RABBITMQ_DLQ, auto_ack=False)
        
        connection.close()
    except Exception as e:
        print(f"Warning: Failed to check DLQ: {e}")
    
    return messages


def clear_dlq():
    """DLQ의 모든 메시지 제거 (테스트 후 정리용)"""
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        method, properties, body = channel.basic_get(queue=RABBITMQ_DLQ, auto_ack=True)
        count = 0
        
        while method:
            count += 1
            method, properties, body = channel.basic_get(queue=RABBITMQ_DLQ, auto_ack=True)
        
        connection.close()
        return count
    except Exception as e:
        print(f"Warning: Failed to clear DLQ: {e}")
        return 0
