"""
文档服务
"""
import logging
import uuid
from typing import List

from fastapi import UploadFile

from app.utils.db import get_cursor
from app.utils.minio_client import upload_file, delete_file, file_exists
from app.schemas.document import DocumentItem
from app.core.config import settings
from app.store.milvus_client import milvus_client

logger = logging.getLogger(__name__)

# MIME 类型映射
MIME_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class DocumentService:
    """文档 CRUD + RustFS 存储"""

    @staticmethod
    def upload(kb_id: str, user_id: str, file: UploadFile) -> DocumentItem:
        """
        上传文档到 RustFS 并写入 DB。

        步骤:
        1. 校验知识库归属
        2. 读取文件内容 → 上传到 RustFS
        3. 写入 tj_documents 记录
        """
        # 1. 校验知识库存在且归属当前用户
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id FROM tj_knowledge_bases WHERE id = %s AND user_id = %s AND status = 1",
                (kb_id, user_id),
            )
            if not cursor.fetchone():
                raise ValueError("知识库不存在或无权操作")

        # 2. 提取文件信息
        original_name = file.filename or "unknown"
        ext = original_name.split(".")[-1].lower() if "." in original_name else "txt"
        title = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
        file_type = ext if ext in MIME_TYPES else "txt"

        # 读取文件内容
        file_data = file.file.read()
        file_size = len(file_data)

        # 3. 上传到 RustFS
        doc_id = uuid.uuid4().hex
        stored_name = f"{doc_id}.{ext}"
        object_path = f"{user_id}/{kb_id}/{stored_name}"

        content_type = MIME_TYPES.get(file_type, "application/octet-stream")
        upload_file(object_path, file_data, content_type)

        # 3.5 上传后验真：stat_object 一次，确认文件在桶里可读
        # 防止 put_object 假成功/路径不一致导致后续 celery 任务空转重试
        if not file_exists(object_path):
            # best-effort 清理残留，避免 bucket 留垃圾
            delete_file(object_path)
            raise RuntimeError(
                f"RustFS 上传后未找到对象: bucket={settings.RUSTFS_BUCKET_NAME} path={object_path}"
            )

        # 4. 写入 DB
        #   file_name = 用户上传的原始文件名（含扩展名），
        #   title     = 去掉扩展名的标题
        #   minio_path 已经包含 UUID 形式的 stored_name，无需再单存一列
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO tj_documents (id, kb_id, user_id, title, file_name, file_type, file_size, minio_path)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (doc_id, kb_id, user_id, title, original_name, file_type, file_size, object_path),
            )

        # 5. DB 写入成功后才触发 Celery（文件已确认存在，不会白转）
        try:
            from app.tasks import parse_document
            parse_document.delay(doc_id)
        except Exception as e:
            logger.warning("Celery 派发失败 doc_id=%s: %s", doc_id, e)

        return DocumentItem(
            id=doc_id,
            kb_id=kb_id,
            title=title,
            file_name=original_name,
            file_type=file_type,
            file_size=file_size,
            parse_status=0,
        )

    @staticmethod
    def list_by_kb(kb_id: str, user_id: str) -> List[DocumentItem]:
        """获取知识库下的文档列表（校验知识库归属）"""
        with get_cursor() as cursor:
            # 先校验知识库归属
            cursor.execute(
                "SELECT id FROM tj_knowledge_bases WHERE id = %s AND user_id = %s AND status = 1",
                (kb_id, user_id),
            )
            if not cursor.fetchone():
                return []

            cursor.execute(
                """
                SELECT id, kb_id, title, file_name, file_type, file_size, parse_status, created_at
                FROM tj_documents
                WHERE kb_id = %s AND status = 1
                ORDER BY created_at DESC
                """,
                (kb_id,),
            )
            rows = cursor.fetchall()

        return [
            DocumentItem(
                id=row["id"],
                kb_id=row["kb_id"],
                title=row["title"],
                file_name=row["file_name"],
                file_type=row["file_type"],
                file_size=row["file_size"],
                parse_status=row["parse_status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    @staticmethod
    def get_by_id(doc_id: str, user_id: str) -> DocumentItem | None:
        """获取单个文档详情（校验用户权限）"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, kb_id, title, file_name, file_type, file_size,
                       minio_path, content_text, parse_status, created_at
                FROM tj_documents
                WHERE id = %s AND user_id = %s AND status = 1
                """,
                (doc_id, user_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return DocumentItem(
            id=row["id"],
            kb_id=row["kb_id"],
            title=row["title"],
            file_name=row["file_name"],
            file_type=row["file_type"],
            file_size=row["file_size"],
            parse_status=row["parse_status"],
            content_text=row["content_text"],
            created_at=row["created_at"],
        )

    @staticmethod
    def delete(doc_id: str, user_id: str) -> bool:
        """
        软删除文档，并清理：
            1. MySQL tj_documents 软删 (status=0)
            2. RustFS 原文件
            3. Milvus 3 个 collection 里该文档的全部 chunk
        校验 user_id 防止越权。
        """
        with get_cursor(commit=True) as cursor:
            # 先查 minio_path
            cursor.execute(
                "SELECT minio_path FROM tj_documents WHERE id = %s AND user_id = %s AND status = 1",
                (doc_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return False

            minio_path = row["minio_path"]

            # 软删除 DB 记录
            cursor.execute(
                "UPDATE tj_documents SET status = 0 WHERE id = %s AND user_id = %s",
                (doc_id, user_id),
            )

        # RustFS 删除文件（失败不影响后续）
        delete_file(minio_path)

        # Milvus 删除该文档的全部 chunk（按 biz_id == doc_id 过滤）
        # biz_id 字段实际存的就是 doc_id（确定性 UUID 字符串）
        milvus_filter = f'biz_id == "{doc_id}"'
        for collection in (
            settings.MILVUS_PARENT_COLLECTION,
            settings.MILVUS_CHILD_COLLECTION,
            settings.MILVUS_BGE_COLLECTION,
        ):
            try:
                if milvus_client.has_collection(collection):
                    milvus_client.delete(
                        collection_name=collection,
                        filter=milvus_filter,
                    )
                    logger.info(
                        "[document.delete] Milvus 已清理 doc_id=%s collection=%s",
                        doc_id, collection,
                    )
            except Exception as e:
                # Milvus 删除失败不阻塞主流程，但记录下来供运维追溯
                logger.error(
                    "[document.delete] Milvus 删除失败 doc_id=%s collection=%s err=%s",
                    doc_id, collection, e,
                )

        return True
