# test/test_05_queue_stability_test.py
"""대기열 안정성 테스트 (GPU 모드, worker 1개 이상에서 실행 가능)"""
import concurrent.futures
import time
import statistics
from test_common import (
    upload_task, wait_for_task_completion, check_rabbitmq_queue_length,
    get_task, API_BASE_URL
)


def test_concurrent_requests(test_sizes: list = None):
    """
    여러 개의 동시 요청 테스트
    
    GPU 모드에서 실행되며, worker 1개만 있어도 모든 작업이 순차적으로 처리됩니다.
    큐 분산 메커니즘과 시스템 안정성을 확인합니다.
    
    Args:
        test_sizes: 테스트할 동시 요청 수 리스트 (기본값: [5, 10])
    """
    if test_sizes is None:
        test_sizes = [5, 10]  # worker 1개여도 처리 가능한 크기
    
    print("ℹ️  GPU mode: All tasks will be processed with GPU inference")
    print("ℹ️  Worker 1개만 있어도 순차 처리로 모든 작업 완료 가능")
    
    results = {}
    
    for size in test_sizes:
        print(f"\n{'='*60}")
        print(f"Testing {size} concurrent requests...")
        print(f"{'='*60}")
        
        task_ids = []
        start_time = time.time()
        upload_errors = []
        
        def upload_request(index):
            try:
                upload_result = upload_task(
                    context=f"테스트 이미지 #{index+1} - 동시 요청 테스트"
                )
                return upload_result['id']
            except Exception as e:
                upload_errors.append(str(e))
                return None
        
        # 동시 요청
        with concurrent.futures.ThreadPoolExecutor(max_workers=size) as executor:
            futures = [executor.submit(upload_request, i) for i in range(size)]
            task_ids = [f.result() for f in futures if f.result() is not None]
        
        upload_time = time.time() - start_time
        upload_success_rate = len(task_ids) / size * 100
        
        print(f"  Upload completed: {len(task_ids)}/{size} succeeded ({upload_success_rate:.1f}%)")
        print(f"  Upload time: {upload_time:.2f}s")
        
        if upload_errors:
            print(f"  Errors: {upload_errors[:3]}")  # 처음 3개만 출력
        
        # RabbitMQ 큐 확인 (큐 분산 메커니즘 확인)
        time.sleep(1)  # 큐에 메시지가 들어갈 시간
        queue_length = check_rabbitmq_queue_length()
        print(f"  Queue length after upload: {queue_length}")
        print(f"  ℹ️  큐 분산 확인: {size}개 요청 중 {queue_length}개가 큐에 대기")
        
        # 모든 작업 완료 대기
        # worker 1개여도 순차 처리 가능하도록 충분한 타임아웃 설정
        # 작업당 약 10-20초 소요 예상, 여유있게 작업 수 * 25초로 설정
        per_task_timeout = max(25 * size, 300)  # 최소 300초 (5분)
        print(f"  Waiting for task completion (timeout: {per_task_timeout}s per task)...")
        
        completion_times = []
        completion_statuses = {'DONE': 0, 'FAILED': 0, 'TIMEOUT': 0}
        
        for idx, task_id in enumerate(task_ids, 1):
            task_start = time.time()
            try:
                task = wait_for_task_completion(task_id, timeout=per_task_timeout)
                elapsed = time.time() - task_start
                completion_times.append(elapsed)
                status = task['status']
                completion_statuses[status] = completion_statuses.get(status, 0) + 1
                
                if status == 'DONE':
                    print(f"    ✓ Task {idx}/{len(task_ids)} completed (DONE) in {elapsed:.1f}s")
                elif status == 'FAILED':
                    print(f"    ✗ Task {idx}/{len(task_ids)} failed (FAILED)")
            except TimeoutError:
                completion_statuses['TIMEOUT'] += 1
                print(f"    ⚠ Task {idx}/{len(task_ids)} timed out after {per_task_timeout}s")
        
        total_time = time.time() - start_time
        
        # GPU 모드: DONE 상태만 성공으로 간주
        done_count = completion_statuses.get('DONE', 0)
        success_criterion = done_count == len(task_ids)
        
        # 큐 분산 확인: 업로드 후 큐에 메시지가 적재되었는지 확인
        queue_worked = queue_length > 0 or len(task_ids) == 0
        
        results[size] = {
            'requested': size,
            'successful_uploads': len(task_ids),
            'upload_success_rate': upload_success_rate,
            'upload_time': upload_time,
            'queue_length_after_upload': queue_length,
            'queue_distribution_worked': queue_worked,
            'completion_statuses': completion_statuses,
            'done_count': done_count,
            'failed_count': completion_statuses.get('FAILED', 0),
            'timeout_count': completion_statuses.get('TIMEOUT', 0),
            'success_criterion_met': success_criterion,
            'avg_completion_time': statistics.mean(completion_times) if completion_times else None,
            'total_time': total_time,
            'server_stable': True  # 에러가 발생하지 않았다면 안정적
        }
        
        print(f"\n  Completion statuses: {completion_statuses}")
        print(f"  ✓ DONE: {done_count}/{len(task_ids)}")
        if completion_statuses.get('FAILED', 0) > 0:
            print(f"  ✗ FAILED: {completion_statuses.get('FAILED', 0)}")
        if completion_statuses.get('TIMEOUT', 0) > 0:
            print(f"  ⚠ TIMEOUT: {completion_statuses.get('TIMEOUT', 0)}")
        print(f"  Queue distribution: {'✓ OK' if queue_worked else '✗ Failed'}")
        if results[size]['avg_completion_time']:
            print(f"  Average completion time: {results[size]['avg_completion_time']:.2f}s")
        print(f"  Total test time: {total_time:.2f}s")
        print(f"  Success criterion met: {'✓ YES' if success_criterion else '✗ NO'}")
    
    # 전체 결과
    overall_success = all(r['success_criterion_met'] for r in results.values())
    
    result = {
        'success': overall_success,
        'test_sizes': test_sizes,
        'mode': 'GPU',
        'results_by_size': results,
        'note': 'GPU mode: All tasks should be DONE. Worker 1개만 있어도 순차 처리로 완료 가능.'
    }
    
    print(f"\n{'='*60}")
    print(f"Queue Stability Test Summary")
    print(f"{'='*60}")
    print(f"Overall success: {'✓ YES' if overall_success else '✗ NO'}")
    print(f"Mode: GPU (all tasks should complete with DONE status)")
    
    return result


if __name__ == '__main__':
    print("ℹ️  GPU 모드로 실행됩니다. 모든 작업이 GPU로 ALT 생성됩니다.")
    print("ℹ️  Worker 1개만 있어도 순차 처리로 모든 작업 완료 가능합니다.")
    print("ℹ️  큐 분산 메커니즘 확인을 위해 autoscaler.py를 백그라운드에서 실행할 수 있습니다.")
    print()
    
    result = test_concurrent_requests(test_sizes=[5, 10])
    print("\nResult:", result)
