from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, engine
from routes import tasks
from src.services.rabbitmq_client import get_rabbitmq_connection, setup_queues
import logging
import sys

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,  # INFO 레벨 이상의 로그 출력
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)  # 표준 출력으로 로그 출력 (Docker 로그에 표시됨)
    ]
)

# 데이터베이스 테이블 생성


init_db()

app = FastAPI(
    title="Altify API",
    description="FastAPI Gateway for Altify",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(tasks.router)


@app.on_event("startup")
def init_rabbitmq():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    setup_queues(channel)  # DLX 및 DLQ 포함 큐 설정
    connection.close()

@app.get("/")
async def root():
    return {"message": "Altify API Gateway"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

