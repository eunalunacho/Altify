from minio import Minio
from minio.error import S3Error
import os
from typing import BinaryIO

# MinIO 클라이언트 설정
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "altify")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "altify2025")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "alt-images")


def get_minio_client() -> Minio:
    """MinIO 클라이언트 인스턴스 반환"""
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE
    )


def ensure_bucket_exists(client: Minio, bucket_name: str = MINIO_BUCKET):
    """버킷이 존재하는지 확인하고 없으면 생성"""
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
    except S3Error as e:
        raise Exception(f"MinIO 버킷 생성 실패: {e}")


def upload_image_to_minio(
    client: Minio,
    file_data: BinaryIO,
    object_name: str,
    bucket_name: str = MINIO_BUCKET
) -> str:
    """
    MinIO에 이미지 업로드
    
    Args:
        client: MinIO 클라이언트
        file_data: 업로드할 파일 데이터 (BinaryIO)
        object_name: MinIO에 저장될 객체 이름
        bucket_name: 버킷 이름
    
    Returns:
        업로드된 이미지의 경로 (버킷/객체명)
    
    Raises:
        Exception: 업로드 실패 시
    """
    try:
        # 버킷 존재 확인 및 생성
        ensure_bucket_exists(client, bucket_name)
        
        # 파일 크기 확인
        file_data.seek(0, 2)  # 파일 끝으로 이동
        file_size = file_data.tell()
        file_data.seek(0)  # 파일 시작으로 이동
        
        # MinIO에 업로드
        client.put_object(
            bucket_name,
            object_name,
            file_data,
            length=file_size,
            content_type="image/jpeg"  # 필요에 따라 동적으로 설정 가능
        )
        
        return f"{bucket_name}/{object_name}"
    except S3Error as e:
        raise Exception(f"MinIO 이미지 업로드 실패: {e}")


def delete_image_from_minio(
    client: Minio,
    image_path: str
) -> bool:
    """
    MinIO에서 이미지 삭제
    
    Args:
        client: MinIO 클라이언트
        image_path: 삭제할 이미지 경로 (버킷명/객체명 형식)
    
    Returns:
        삭제 성공 여부
    
    Raises:
        Exception: 삭제 실패 시
    """
    try:
        # 경로에서 버킷명과 객체명 분리
        if "/" not in image_path:
            raise ValueError(f"잘못된 이미지 경로 형식: {image_path}")
        
        bucket_name, object_name = image_path.split("/", 1)
        
        # MinIO에서 객체 삭제
        client.remove_object(bucket_name, object_name)
        return True
    except S3Error as e:
        raise Exception(f"MinIO 이미지 삭제 실패: {e}")
    except Exception as e:
        raise Exception(f"이미지 삭제 중 오류 발생: {e}")
