"""
RustFS / MinIO 客户端（S3 兼容协议）
"""
import logging
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


def get_minio_client() -> Minio:
    """获取 MinIO 客户端单例（兼容 RustFS S3 协议）"""
    global _client
    if _client is None:
        _client = Minio(
            endpoint=f"{settings.RUSTFS_ADDRESS}:{settings.RUSTFS_PORT}",
            access_key=settings.RUSTFS_ACCESS_KEY_ID,
            secret_key=settings.RUSTFS_SECRET_ACCESS_KEY,
            secure=settings.RUSTFS_USE_SSL,
            region=settings.RUSTFS_REGION,
        )
        # 确保 bucket 存在
        bucket = settings.RUSTFS_BUCKET_NAME
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket)
    return _client


def upload_file(object_path: str, file_data: bytes, content_type: str) -> str:
    """
    上传文件到 RustFS。

    参数:
        object_path: 对象存储路径，如 "user123/kb456/doc789.pdf"
        file_data: 文件二进制内容
        content_type: MIME 类型

    返回:
        对象的完整路径

    抛出:
        RuntimeError: 上传失败（网络/存储不可用等）
    """
    client = get_minio_client()
    bucket = settings.RUSTFS_BUCKET_NAME
    try:
        client.put_object(
            bucket_name=bucket,
            object_name=object_path,
            data=BytesIO(file_data),
            length=len(file_data),
            content_type=content_type,
        )
    except S3Error as e:
        logger.error("[minio] 上传失败 bucket=%s path=%s code=%s err=%s", bucket, object_path, e.code, e)
        raise RuntimeError(f"文件存储失败（{e.code}），请稍后重试") from e
    return object_path


def delete_file(object_path: str) -> bool:
    """
    从 RustFS 删除文件。

    返回:
        True 表示删除成功，False 表示文件不存在或删除失败
    """
    client = get_minio_client()
    bucket = settings.RUSTFS_BUCKET_NAME
    try:
        client.remove_object(bucket, object_path)
        return True
    except S3Error:
        return False


def file_exists(object_path: str) -> bool:
    """
    检查 RustFS 中对象是否存在（用于上传后验证）

    返回:
        True 表示存在，False 表示不存在
    """
    client = get_minio_client()
    bucket = settings.RUSTFS_BUCKET_NAME
    try:
        client.stat_object(bucket, object_path)
        return True
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            return False
        logger.error(
            "[minio] stat 失败 bucket=%s path=%s code=%s err=%s",
            bucket, object_path, exc.code, exc,
        )
        return False


def get_file(object_path: str) -> bytes | None:
    """
    从 RustFS 下载文件内容。

    返回:
        文件二进制内容，不存在时返回 None
    """
    client = get_minio_client()
    bucket = settings.RUSTFS_BUCKET_NAME
    try:
        response = client.get_object(bucket, object_path)
        try:
            data = response.read()
        finally:
            # urllib3 v2 已无 release_connection()，仅 close() 即可
            response.close()
        return data
    except S3Error as exc:
        # NoSuchKey/NoSuchObject/NoSuchBucket = 文件不存在
        if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            logger.info(
                "[minio] 文件不存在 bucket=%s path=%s code=%s",
                bucket, object_path, exc.code,
            )
        else:
            logger.error(
                "[minio] 下载失败 bucket=%s path=%s code=%s err=%s",
                bucket, object_path, exc.code, exc,
            )
        return None
