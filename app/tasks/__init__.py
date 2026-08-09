"""
文档处理任务链

管线：
    parse_document（轻量解析）→ chunk_and_vectorize（切片 + 向量化）

解析策略（按文件类型分发，覆盖 80%+ 场景）：
    - pdf   → pymupdf4llm（输出 Markdown，保留表格）
    - docx  → python-docx
    - pptx  → python-pptx
    - xlsx  → pandas
    - txt/csv/md → 直接读取
    - 图片/扫描件 → PaddleOCR（可选，默认关闭）

队列分配：
    parse 队列 — parse_document（CPU 中等，单文件轻量）
    embed 队列 — chunk_and_vectorize（IO 密集）
"""
import logging
from io import BytesIO

from app.celery_app import celery_app
from app.core.config import settings
from app.services.embedding_service import EmbeddingService
from app.store.milvus_client import milvus_client

from app.tasks.parsers import parse_by_type
from app.tasks.splitter import basic_custom_splitter, SplitterConfig
from app.utils.db import get_cursor
from app.utils.minio_client import get_file

logger = logging.getLogger(__name__)


# ==================== 第 1 步：轻量文档解析 ====================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="parse")
def parse_document(self, doc_id: str):
    """
    从 RustFS 下载文件 → 按文件类型分发解析 → 写入 content_text（Markdown）。
    """
    logger.info("[parse_document] 开始处理 doc_id=%s", doc_id)

    try:
        _update_parse_status(doc_id, status=1)
        _parse_document_lightweight(doc_id)
        _update_parse_status(doc_id, status=2)
        # 触发下一步：切片 + 向量化
        chunk_and_vectorize.delay(doc_id)
    except FileNotFoundError as exc:
        # 永久失败：文件在 RustFS 里就是没有，重试无用
        logger.error("[parse_document] 永久失败 doc_id=%s: %s", doc_id, exc)
        _update_parse_status(doc_id, -1)
        # 不 raise，不 retry
    except Exception as exc:
        logger.error("[parse_document] 解析失败 doc_id=%s: %s", doc_id, exc)
        _update_parse_status(doc_id, -1)
        raise self.retry(exc=exc)


# ==================== 第 2 步：切片 + 向量化 ====================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="embed")
def chunk_and_vectorize(self, doc_id: str):
    """
    读取 content_text → Parent-Child 切分 → 写入 Milvus 三个 collection。
    """
    logger.info("[chunk_and_vectorize] 开始切片 doc_id=%s", doc_id)

    try:
        doc_id, result = _chunk_document(doc_id)

        # 1. 写入 parent collection
        if result.parent_chunks:
            milvus_client.insert(
                collection_name=settings.MILVUS_PARENT_COLLECTION,
                data=[_doc_to_parent_row(doc, doc_id) for doc in result.parent_chunks],
            )

        # 2. 写入 child text collection（纯 BM25）
        if result.child_chunks:
            milvus_client.insert(
                collection_name=settings.MILVUS_CHILD_COLLECTION,
                data=[_doc_to_row(doc, doc_id) for doc in result.child_chunks],
            )

            # 3. 计算 BGE 向量 + 写入 bge collection
            texts = [doc.page_content for doc in result.child_chunks]
            vectors = EmbeddingService.embed_texts(texts)

            milvus_client.insert(
                collection_name=settings.MILVUS_BGE_COLLECTION,
                data=[
                    {**_doc_to_row(doc, doc_id), "vector": vec}
                    for doc, vec in zip(result.child_chunks, vectors)
                ],
            )

        logger.info(
            "[chunk_and_vectorize] 完成 doc_id=%s parent=%d child=%d",
            doc_id, len(result.parent_chunks), len(result.child_chunks),
        )

    except FileNotFoundError as exc:
        # 永久失败：文档在 DB 里就不存在 / content_text 为空，重试无用
        logger.error("[chunk_and_vectorize] 永久失败 doc_id=%s: %s", doc_id, exc)
        # 不 raise，不 retry
    except Exception as exc:
        logger.error("[chunk_and_vectorize] 失败 doc_id=%s: %s", doc_id, exc)
        raise self.retry(exc=exc)


# ==================== 内部函数 ====================

def _chunk_document(doc_id: str):
    """从 DB 读 content_text，调 basic_custom_splitter 切分"""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, content_text, file_name FROM tj_documents WHERE id = %s",
            (doc_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise FileNotFoundError(f"tj_documents 不存在: {doc_id}")

    content_text = row["content_text"] or ""
    file_name = row["file_name"]
    if not content_text:
        logger.warning("[chunk_and_vectorize] content_text 为空 doc_id=%s", doc_id)

    # biz_id 字段直接存 doc_id（UUID 字符串），保证跨进程一致 → 可按 doc_id 精准删除
    biz_id = doc_id

    config = SplitterConfig()
    result = basic_custom_splitter(
        biz_id=biz_id,
        document_context=content_text,
        config=config,
        enable_raptor=False,
        data_name=file_name,
    )
    return doc_id, result


def _doc_to_row(doc, biz_id: str) -> dict:
    """Document → Milvus 行（基础字段，无 created_at/vector）
    注：biz_id 字段实际存的是 doc_id（确定性 UUID 字符串），用于按文档删除。
    """
    md = dict(doc.metadata or {})
    return {
        "text": doc.page_content,
        "biz_id": str(md.get("biz_id", biz_id)),
        "chunk_id": str(md.get("chunk_id", "")),
        "index_id": float(md.get("index_id", 0)),
    }


def _doc_to_parent_row(doc, biz_id: str) -> dict:
    """Document → parent collection 行（含 created_at）"""
    row = _doc_to_row(doc, biz_id)
    md = dict(doc.metadata or {})
    row["created_at"] = int(md.get("created_at", 0))
    return row


def _update_parse_status(doc_id: str, status: int):
    """更新文档解析状态"""
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE tj_documents SET parse_status = %s WHERE id = %s",
            (status, doc_id),
        )


def _parse_document_lightweight(doc_id: str):
    """
    轻量级文档解析（按文件类型分发），结果写入 tj_documents.content_text。
    """
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT minio_path, file_type, file_name FROM tj_documents WHERE id = %s",
            (doc_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"文档不存在: {doc_id}")

    file_type = (row["file_type"] or "").lower()
    file_name = row["file_name"]
    minio_path = row["minio_path"]

    logger.info(
        "[parse_document] 开始解析 doc_id=%s file=%s type=%s",
        doc_id, file_name, file_type,
    )

    file_bytes = get_file(minio_path)
    if file_bytes is None:
        raise FileNotFoundError(f"RustFS 文件不存在: {minio_path}")

    text = parse_by_type(file_type, file_bytes)
    if not text:
        logger.warning("[parse_document] 解析结果为空 doc_id=%s type=%s", doc_id, file_type)

    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE tj_documents SET content_text = %s WHERE id = %s",
            (text, doc_id),
        )

    logger.info(
        "[parse_document] 解析完成 doc_id=%s type=%s text_len=%d",
        doc_id, file_type, len(text),
    )
