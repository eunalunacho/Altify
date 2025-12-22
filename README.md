# Altify

Altify는 LLaVA(Large Language and Vision Assistant) 모델을 활용한 ALT 텍스트 자동 생성 플랫폼입니다. 이미지와 문맥 정보를 입력받아 2개의 ALT 텍스트 후보를 생성하며, 사용자가 최종 ALT 텍스트를 검토하고 승인할 수 있습니다.

<br>

## 주요 기능

- **이미지 업로드 및 ALT 텍스트 생성**: 이미지와 문맥 텍스트를 업로드하여 AI 기반 ALT 텍스트 생성
- **블로그 HTML 파싱**: 블로그 HTML을 입력받아 이미지와 문맥을 자동 추출하여 일괄 처리
- **다중 후보 생성**: 각 이미지마다 2개의 다양한 ALT 텍스트 후보 제공
- **비동기 처리**: RabbitMQ를 통한 비동기 작업 큐 처리
- **자동 스케일링**: 대기열 깊이에 따른 워커 자동 스케일링

<br>

## 기술 스택

- **Frontend**: React.js, Vite, Tailwind CSS
- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **Worker**: Python, aio-pika, LLaVA-1.5-7B (4-bit 양자화)
- **Database**: PostgreSQL
- **Message Broker**: RabbitMQ (DLQ 지원)
- **Object Storage**: MinIO
- **Infrastructure**: Docker, Docker Compose

<br>

## 사전 요구사항

### 1. 환경 설정

#### Windows 환경
- **WSL2 (Windows Subsystem for Linux 2)** 설치 및 설정
- **Docker Desktop** 설치 (WSL2 백엔드 사용)
- **NVIDIA GPU 드라이버** 설치 (워커 서비스용)
- **NVIDIA Container Toolkit** 설치

#### Linux 환경
- Docker 및 Docker Compose 설치
- NVIDIA GPU 드라이버 및 NVIDIA Container Toolkit 설치

### 2. GPU 요구사항

워커 서비스는 GPU를 사용하여 LLaVA 모델을 실행합니다:
- NVIDIA GPU (CUDA 지원)
- 최소 8GB VRAM 권장 (4-bit 양자화 사용 시)

### 3. 환경 변수 설정 

프로젝트 루트에 `.env` 파일을 통해 환경 변수를 설정할 수 있습니다.
(github에는 포함되어있지 않음, zip 파일에 포함됨됨)

<br>

## 실행 방법

### 1. 프로젝트 클론

```bash
git clone <repository-url>
cd Altify
```

### 2. Docker 컨테이너 실행

```bash
# 모든 서비스 시작 (백그라운드)
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 특정 서비스 로그만 확인
docker-compose logs -f api
docker-compose logs -f worker
```

### 3. 서비스 접속

서비스가 정상적으로 시작되면 다음 URL로 접속할 수 있습니다:

- **Frontend**: http://localhost:3000
- **API Gateway**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **RabbitMQ Management UI**: http://localhost:15672 (id/pw는 .env 참고)
- **MinIO Console**: http://localhost:9001 (id/pw는 .env 참고)

### 4. 서비스 중지

```bash
# 모든 서비스 중지
docker-compose down

# 볼륨까지 삭제 (데이터 삭제)
docker-compose down -v
```

### 5. 워커 자동 스케일링 (선택사항)

대기열 깊이에 따라 워커 수를 자동으로 조정하려면 시스템을 실행한 뒤 백그라운드에서서 `autoscaler.py`를 실행합니다:

```bash
python autoscaler.py
```
<br>

## 테스트 실행 방법

프로젝트의 테스트는 `test/` 디렉토리에 있으며, 시스템의 성공 기준(Success Criteria)을 검증합니다.

### 사전 요구사항

1. **Docker 컨테이너 실행 중**
   ```bash
   docker-compose up -d
   ```

2. **Python 패키지 설치** (가상환경 생성 추천천)
   ```bash
   cd test
   pip install -r requirements.txt
   ```


### 테스트 실행

#### 개별 테스트 실행

```bash
# test 디렉토리로 이동
cd test

# E2E 파이프라인 테스트
python test_01_e2e_pipeline_test.py

# 비동기 응답 시간 테스트
python test_02_async_response_test.py

# 다중 후보 생성 테스트
python test_03_multi_candidate_test.py

# 하드웨어 제약 테스트 (워커 컨테이너 내부에서 실행)
docker exec altify-worker-1 mkdir -p /app/test
docker cp ./test/test_04_hardware_test.py altify-worker-1:/app/test/
docker exec altify-worker-1 python /app/test/test_04_hardware_test.py

# 대기열 안정성 테스트 (autoscaler와 함께)
# Terminal 1: autoscaler 실행
python ../autoscaler.py

# Terminal 2: 테스트 실행
python test_05_queue_stability_test.py

# 트랜잭션 롤백 테스트
python test_06_transaction_rollback_test.py

# DLQ 복구 테스트
python test_07_dlq_recovery_test.py
```

<br>

### 특별 참고사항

#### SC-04 (하드웨어 제약 테스트)

워커 컨테이너 내부에서 실행해야 합니다:

```bash
# 1. 컨테이너 내부에 test 디렉토리 생성
docker exec altify-worker-1 mkdir -p /app/test

# 2. 파일 복사
docker cp ./test/test_04_hardware_test.py altify-worker-1:/app/test/

# 3. 실행
docker exec altify-worker-1 python /app/test/test_04_hardware_test.py
```

#### SC-05 (대기열 안정성 테스트)

`autoscaler.py`를 백그라운드에서 실행한 상태에서 테스트해야 합니다:

```bash
# Terminal 1: autoscaler 실행
python ../autoscaler.py

# Terminal 2: 테스트 실행
python test_05_queue_stability_test.py
```
<br>

### 문제 해결

#### ImportError 발생 시

```bash
cd test
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### API 연결 실패

- `docker-compose ps`로 모든 컨테이너가 실행 중인지 확인
- `API_BASE_URL` 환경 변수가 올바른지 확인
- 방화벽 설정 확인

#### RabbitMQ 연결 실패

- RabbitMQ Management UI 접속 확인: http://localhost:15672
- 인증 정보 확인 
- `RABBITMQ_HOST`, `RABBITMQ_PORT` 환경 변수 확인



## 프로젝트 구조

```
Altify/
├── backend/          # FastAPI 백엔드 서비스
├── frontend/         # React 프론트엔드
├── worker/          # LLaVA 워커 서비스
├── test/            # 테스트 코드
├── docker-compose.yml
├── autoscaler.py    # 워커 자동 스케일링 스크립트
└── README.md
```


