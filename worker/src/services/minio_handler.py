from minio import Minio
from minio.error import S3Error
from PIL import Image
import io
import os
import logging

logger = logging.getLogger(__name__)

# MinIO 클라이언트 설정
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "altify")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "altify2025")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"


def get_minio_client() -> Minio:
    """MinIO 클라이언트 인스턴스 반환"""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )


def download_image_from_minio(image_path: str) -> Image.Image:
    """
    MinIO에서 이미지를 다운로드하여 PIL Image 객체로 반환
    
    Args:
        image_path: MinIO에 저장된 이미지 경로 (버킷명/객체명 형식)
    
    Returns:
        PIL Image 객체 (RGB 모드)
    
    Raises:
        Exception: 다운로드 실패 시
    """
    try:
        # 경로에서 버킷명과 객체명 분리
        if "/" not in image_path:
            raise ValueError(f"잘못된 이미지 경로 형식: {image_path}")
        
        bucket_name, object_name = image_path.split("/", 1)
        
        logger.info(f"MinIO에서 이미지 다운로드 중: {bucket_name}/{object_name}")
        
        # MinIO 클라이언트 생성
        client = get_minio_client()
        
        # 이미지 데이터 다운로드
        response = client.get_object(bucket_name, object_name)
        image_data = response.read()
        response.close()
        response.release_conn()
        
        # BytesIO로 변환 후 PIL Image로 로드
        image_stream = io.BytesIO(image_data)
        image = Image.open(image_stream)
        
        # RGB 모드로 변환 (RGBA, L 등 다른 모드 처리)
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        logger.info(f"이미지 다운로드 완료: {image.size}, 모드: {image.mode}")
        
        return image
        
    except S3Error as e:
        logger.error(f"MinIO S3 오류: {str(e)}")
        raise Exception(f"MinIO 이미지 다운로드 실패: {str(e)}")
    except Exception as e:
        logger.error(f"이미지 다운로드 중 오류 발생: {str(e)}")
        raise Exception(f"이미지 다운로드 실패: {str(e)}")

