# LLaVA AI Worker Dockerfile (CUDA 지원)
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Python 및 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# python 명령어 심볼릭 링크 설정
RUN ln -s /usr/bin/python3 /usr/bin/python

# 작업 디렉토리 설정
WORKDIR /app

ENV PYTHONPATH="${PYTHONPATH}:/app"

# 의존성 파일 복사 및 설치 (캐싱 효율을 위해 먼저 복사)
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ ./src/

# 실행 명령
CMD ["python", "src/main.py"]

