# test/test_02_async_response_test.py
"""비동기 응답 시간 테스트"""
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from test_common import upload_task, API_BASE_URL


def test_async_response_time(num_requests: int = 100):
    """
    여러 요청을 보내고 응답 시간 측정
    
    Args:
        num_requests: 요청 횟수 (기본값: 100)
    """
    response_times = []
    errors = []
    
    def single_request():
        try:
            start = time.time()
            upload_result = upload_task()
            elapsed = (time.time() - start) * 1000  # ms
            assert upload_result['status'] == 202, f"Expected 202, got {upload_result['status']}"
            assert elapsed < 1000, f"Response time {elapsed}ms exceeds 1s limit"
            return elapsed
        except Exception as e:
            errors.append(str(e))
            return None
    
    print(f"Sending {num_requests} requests...")
    
    # 동시 요청 (최대 10개 동시)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(single_request) for _ in range(num_requests)]
        response_times = [f.result() for f in futures if f.result() is not None]
    
    if len(response_times) < num_requests * 0.9:  # 90% 이상 성공해야 함
        return {
            'success': False,
            'error': f'Too many failures: {len(response_times)}/{num_requests} succeeded',
            'errors': errors[:5]  # 처음 5개 에러만
        }
    
    all_under_1s = all(t < 1000 for t in response_times)
    
    result = {
        'success': all_under_1s,
        'total_requests': num_requests,
        'successful_requests': len(response_times),
        'mean': statistics.mean(response_times),
        'median': statistics.median(response_times),
        'min': min(response_times),
        'max': max(response_times),
        'all_under_1s': all_under_1s
    }
    
    # P95, P99 계산
    if len(response_times) >= 20:
        quantiles = statistics.quantiles(response_times, n=20)
        result['p95'] = quantiles[18]
    if len(response_times) >= 100:
        quantiles = statistics.quantiles(response_times, n=100)
        result['p99'] = quantiles[98]
    
    print(f"\n✓ Async Response Test: {len(response_times)}/{num_requests} succeeded")
    print(f"  Mean: {result['mean']:.2f}ms, Median: {result['median']:.2f}ms")
    print(f"  Min: {result['min']:.2f}ms, Max: {result['max']:.2f}ms")
    if 'p95' in result:
        print(f"  P95: {result['p95']:.2f}ms")
    if 'p99' in result:
        print(f"  P99: {result['p99']:.2f}ms")
    print(f"  All under 1s: {all_under_1s}")
    
    return result


if __name__ == '__main__':
    result = test_async_response_time(50)  # 테스트용으로 50개만
    print("\nResult:", result)
