from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, engine
from routes import tasks
from src.services.rabbitmq_client import get_rabbitmq_connection, RABBITMQ_QUEUE

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
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    connection.close()

@app.get("/")
async def root():
    return {"message": "Altify API Gateway"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

