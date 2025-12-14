import asyncio
import logging
import sys
import os

from src.core.model import model_loader
from src.consumer import start_consumer

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

async def warmup_model():
    logger.info("모델 Pre-warm 시작...")
    # ✅ 동기/무거운 작업을 별도 스레드에서 실행
    await asyncio.to_thread(model_loader.load)
    logger.info("모델 Pre-warm 완료!")


async def main():
    """메인 함수"""
    logger.info("=" * 50)
    logger.info("LLaVA AI Worker 시작")
    logger.info("=" * 50)
    
    await warmup_model()

    try:
        # 1. Consumer 실행
        logger.info("Consumer 시작...")
        await start_consumer()
        
    except KeyboardInterrupt:
        logger.info("작업자 종료 요청 수신")
    except Exception as e:
        logger.error(f"작업자 실행 중 오류 발생: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("작업자 종료")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("프로그램 종료")
    except Exception as e:
        logger.error(f"프로그램 실행 중 오류: {str(e)}", exc_info=True)
        sys.exit(1)

