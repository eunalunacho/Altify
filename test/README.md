# 테스트 실행 가이드

## 개요

이 디렉토리에는 Altify 시스템의 성공 기준(Success Criteria)을 검증하는 테스트들이 포함되어 있습니다.

## 테스트 구조

- `test_common.py`: 공통 유틸리티 함수 (API 호출, 큐 확인 등)
- `test_01_e2e_pipeline_test.py`: SC-01 - End-to-End 파이프라인 테스트
- `test_02_async_response_test.py`: SC-02 - 비동기 응답 시간 테스트
- `test_03_multi_candidate_test.py`: SC-03 - 다중 후보 생성 테스트
- `test_04_hardware_test.py`: SC-04 - 하드웨어 제약 테스트
- `test_05_queue_stability_test.py`: SC-05 - 대기열 안정성 테스트
- `test_06_transaction_rollback_test.py`: SC-06 - 트랜잭션 롤백 테스트
- `test_07_dlq_recovery_test.py`: SC-07 - DLQ 복구 테스트
- `00_integration_test_suite.py`: 모든 테스트를 실행하는 통합 스위트

## 사전 요구사항

1. Docker 컨테이너 실행 중:
   ```bash
   docker-compose up -d
   ```

2. Python 패키지 설치:
   ```bash
   # 전체 패키지 설치 
   pip install -r requirements.txt
   ```

3. 환경 변수 설정 (선택사항):
   ```bash
   export API_BASE_URL=http://localhost:8000
   export RABBITMQ_HOST=localhost
   export RABBITMQ_API_URL=http://localhost:15672/api
   ```

## 실행 방법
### 개별 테스트 실행

```bash
# E2E 파이프라인 테스트
python test_01_e2e_pipeline_test.py

# 비동기 응답 시간 테스트
python test_02_async_response_test.py

# 다중 후보 생성 테스트
python test_03_multi_candidate_test.py

# 하드웨어 제약 테스트 (워커 컨테이너 내부에서 실행)
## 1. 컨테이너 내부에 test 디렉토리 생성
docker exec altify-worker-1 mkdir -p /app/test
## 2. 파일 복사
docker cp ./test/test_04_hardware_test.py altify-worker-1:/app/test/
## 3. 실행
docker exec altify-worker-1 python /app/test/test_04_hardware_test.py


# 대기열 안정성 테스트 (autoscaler와 함께)
python ../autoscaler.py
python test_05_queue_stability_test.py

# 트랜잭션 롤백 테스트
python test_06_transaction_rollback_test.py

# DLQ 복구 테스트
python test_07_dlq_recovery_test.py
```

## 특별 참고사항

### SC-04 (하드웨어 제약 테스트)

워커 컨테이너 내부에서 실행해야 합니다.
컨테이너 내부로 파일을 복사한 후 실행:

```bash
## 1. 컨테이너 내부에 test 디렉토리 생성
docker exec altify-worker-1 mkdir -p /app/test
## 2. 파일 복사
docker cp ./test/test_04_hardware_test.py altify-worker-1:/app/test/
## 3. 실행
docker exec altify-worker-1 python /app/test/test_04_hardware_test.py
```

### SC-05 (대기열 안정성 테스트)

`autoscaler.py`를 백그라운드에서 실행한 상태에서 테스트해야 합니다:

```bash
# Terminal 1: autoscaler 실행
python ../autoscaler.py

# Terminal 2: 테스트 실행
python test_05_queue_stability_test.py
```

CPU 모드에서는 GPU 추론은 실패하지만, 큐 분산 메커니즘은 정상적으로 테스트됩니다.


## 문제 해결
### ImportError 발생 시

```bash
# test 디렉토리로 이동
cd test

# Python path 추가
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### API 연결 실패

- `docker-compose ps`로 모든 컨테이너가 실행 중인지 확인
- `API_BASE_URL` 환경 변수가 올바른지 확인
- 방화벽 설정 확인

### RabbitMQ 연결 실패

- RabbitMQ Management UI 접속 확인: http://localhost:15672
- 인증 정보 확인
- `RABBITMQ_HOST`, `RABBITMQ_PORT` 환경 변수 확인
