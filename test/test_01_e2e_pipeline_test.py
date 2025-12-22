# test/test_01_e2e_pipeline_test.py
"""E2E 파이프라인 테스트"""
import time
import requests
from test_common import (
    API_BASE_URL, upload_task, wait_for_task_completion, 
    check_rabbitmq_queue_length, get_task
)


def test_e2e_pipeline():
    """
    전체 파이프라인 추적:
    1. 이미지 업로드 → API 응답 시간
    2. RabbitMQ 큐 적재 확인
    3. Worker 소비 및 추론 완료 시간
    4. DB 결과 저장 확인
    5. Frontend 조회 가능 여부
    """
    timestamps = {}
    
    try:
        # 1. 업로드 시작
        print("Step 1: Uploading task...")
        timestamps['upload_start'] = time.time()
        upload_result = upload_task()
        task_id = upload_result['id']
        timestamps['upload_response'] = time.time()
        upload_time = timestamps['upload_response'] - timestamps['upload_start']
        print(f"  ✓ Upload completed in {upload_time:.2f}s, task_id: {task_id}")
        
        # 2. RabbitMQ 큐 확인 (약간의 지연 후 확인)
        print("Step 2: Checking RabbitMQ queue...")
        time.sleep(0.5)  # 큐에 메시지가 들어갈 시간
        queue_length = check_rabbitmq_queue_length()
        timestamps['queue_checked'] = time.time()
        print(f"  ✓ Queue length: {queue_length}")
        
        # 3. Worker 처리 대기 (폴링)
        print("Step 3: Waiting for worker processing...")
        task = wait_for_task_completion(task_id, timeout=300)
        timestamps['worker_done'] = time.time()
        
        if task['status'] == 'FAILED':
            return {
                'success': False,
                'error': 'Task failed',
                'task_status': task['status']
            }
        
        processing_time = timestamps['worker_done'] - timestamps['upload_response']
        print(f"  ✓ Processing completed in {processing_time:.2f}s")
        
        # 4. DB 저장 확인
        print("Step 4: Verifying DB storage...")
        assert task['alt_generated_1'] is not None, "alt_generated_1 is None"
        assert task['alt_generated_2'] is not None, "alt_generated_2 is None"
        timestamps['db_verified'] = time.time()
        print(f"  ✓ ALT 1: {task['alt_generated_1'][:50]}...")
        print(f"  ✓ ALT 2: {task['alt_generated_2'][:50]}...")
        
        # 5. API 조회 테스트 (Frontend는 API를 통해 조회)
        print("Step 5: Testing API access...")
        api_task = get_task(task_id)
        assert api_task['id'] == task_id
        timestamps['api_accessible'] = time.time()
        print(f"  ✓ API access verified")
        
        # 계산
        total_time = timestamps['api_accessible'] - timestamps['upload_start']
        
        result = {
            'success': True,
            'task_id': task_id,
            'total_time': total_time,
            'breakdown': {
                'upload_to_response': timestamps['upload_response'] - timestamps['upload_start'],
                'response_to_queue': timestamps['queue_checked'] - timestamps['upload_response'],
                'queue_to_worker_start': 0,  # 정확한 시간은 측정 불가
                'worker_processing': timestamps['worker_done'] - timestamps['queue_checked'],
                'db_verification': timestamps['db_verified'] - timestamps['worker_done'],
                'api_access': timestamps['api_accessible'] - timestamps['db_verified']
            },
            'alt1': task['alt_generated_1'],
            'alt2': task['alt_generated_2']
        }
        
        print(f"\n✓ E2E Pipeline Test PASSED")
        print(f"  Total time: {total_time:.2f}s")
        return result
        
    except AssertionError as e:
        return {'success': False, 'error': f'Assertion failed: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == '__main__':
    result = test_e2e_pipeline()
    print("\nResult:", result)
