"""
Parent-Child 文档切分器

设计：
    - 先按 parent_chunk_size 切成 parent chunks（粗粒度，保留上下文）
    - 再按 child_chunk_size 把每个 parent 切成更细的 child chunks（用于向量化检索）
    - 每个 child 通过 parent_id 关联回 parent

适用场景：
    - 检索时用 child（精细匹配）
    - 召回后用 parent 重新构造上下文给 LLM
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
from app.utils.ids_generator import generate_unique_uuids


# ==================== 配置 & 结果结构 ====================

class PretreatmentMethods(BaseModel):
    replace_continuous_whitespace_pattern: bool = False
    remove_all_url_and_email_address: bool = False

@dataclass
class SplitterConfig:
    """切分器配置"""
    # 默认按 Markdown 友好的分隔符顺序：段落 > 行 > 句 > 字
    separators: List[str] = field(default_factory=lambda: ["\n\n\n", "\n\n", "\n", " ", ""])
    pretreatment_methods: PretreatmentMethods = Field(default_factory=PretreatmentMethods)
    parent_chunk_size: int = 2048
    child_chunk_size: int = 512
    overlap_size: int = 100


@dataclass
class ParentChildSplitterChunk:
    """Parent-Child 切分结果"""
    parent_chunks: List[Document] = field(default_factory=list)
    child_chunks: List[Document] = field(default_factory=list)


# ==================== 工具函数 ====================

def _prepend_filename(doc: Document, data_name: Optional[str]) -> None:
    """在 chunk 开头追加"文件名：xxx"行（幂等，避免重复加）"""
    if not data_name:
        return

    prefix = f"文件名：{data_name}\n"
    if doc.page_content.startswith(prefix):
        return

    doc.page_content = prefix + doc.page_content


# ==================== 主切分函数 ====================

def basic_custom_splitter(
    biz_id: int,
    document_context: str,
    config: SplitterConfig,
    enable_raptor: bool = False,
    data_name: Optional[str] = None,
) -> ParentChildSplitterChunk:
    """
    Parent-Child 双层切分。

    Args:
        biz_id: 业务 ID（如文档 ID）
        document_context: 待切分的文本（一般是 PDF/DOCX 解析后的 Markdown）
        config: 切分器配置
        enable_raptor: 是否启用 RAPTOR 递归摘要（暂未实现）
        data_name: 文件名，会拼接到每个 chunk 开头（便于 LLM 知道出处）

    Returns:
        ParentChildSplitterChunk（含 parent_chunks 和 child_chunks）

    每个 chunk 的 metadata 包含：
        - biz_id:      业务 ID
        - chunk_id:    UUID（parent 自己的；child 继承自 parent）
        - index_id:    1000 * (idx + 1)，给 child 预留位置
        - chunk_type:  "parent" 或 "child"
        - parent_id:   仅 child 有，指向 parent 的 chunk_id
        - created_at:  毫秒时间戳（parent 用基准值，child 在此基础上递增）
    """
    # 1. 先切 parent
    parent_splitter = RecursiveCharacterTextSplitter(
        separators=config.separators,
        chunk_size=config.parent_chunk_size,
        chunk_overlap=config.overlap_size,
    )
    parent_chunks = parent_splitter.split_documents([Document(page_content=document_context)])

    chunk_ids = generate_unique_uuids(len(parent_chunks))
    base_timestamp = int(datetime.now().timestamp() * 1000)

    # 2. 给 parent 打 metadata
    for idx, parent_chunk in enumerate(parent_chunks):
        _prepend_filename(parent_chunk, data_name)
        parent_chunk.metadata["biz_id"] = biz_id
        parent_chunk.metadata["chunk_id"] = chunk_ids[idx]
        parent_chunk.metadata["index_id"] = 1000 * (idx + 1)
        parent_chunk.metadata["created_at"] = base_timestamp + idx
        parent_chunk.metadata["chunk_type"] = "parent"

    # 3. RAPTOR 模式：parent 同时作为 child 返回（不进一步细分）
    if enable_raptor:
        return ParentChildSplitterChunk(
            parent_chunks=parent_chunks,
            child_chunks=deepcopy(parent_chunks),
        )

    # 4. 正常模式：每个 parent 再切 child
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.child_chunk_size,
        chunk_overlap=config.overlap_size,
    )

    child_chunks_list: List[Document] = []
    for idx, parent_chunk in enumerate(parent_chunks):
        parent_chunk_id = parent_chunk.metadata["chunk_id"]
        parent_created_at = parent_chunk.metadata["created_at"]

        children = child_splitter.split_documents([parent_chunk])
        for child_idx, child_chunk in enumerate(children):
            # child 重新建立干净的 metadata，只保留关联信息
            child_chunk.metadata = {
                "biz_id": biz_id,
                "chunk_id": generate_unique_uuids(1)[0],
                "parent_id": parent_chunk_id,
                "index_id": parent_chunk.metadata["index_id"] + child_idx + 1,
                "created_at": parent_created_at + (child_idx + 1) * 0.001,
                "chunk_type": "child",
            }
            child_chunks_list.append(child_chunk)

    return ParentChildSplitterChunk(
        parent_chunks=parent_chunks,
        child_chunks=child_chunks_list,
    )