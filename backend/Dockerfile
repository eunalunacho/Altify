# FastAPI Backend Dockerfile
FROM python:3.10-slim

# 시스템 패키지 설치 (PostgreSQL 연결용)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

ENV PYTHONPATH="${PYTHONPATH}:/app/src"

# 의존성 파일 복사 및 설치 (캐싱 효율을 위해 먼저 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ ./src/

# 포트 노출
EXPOSE 8000

# 실행 명령
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

