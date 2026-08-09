-- ============================================
-- AIGC 文档切片表（Celery 异步处理管线用）
-- 依赖：tj_documents 表已存在
-- ============================================

CREATE TABLE IF NOT EXISTS tj_document_chunks (
    id            VARCHAR(32)  NOT NULL PRIMARY KEY  COMMENT 'UUID hex',
    document_id   VARCHAR(32)  NOT NULL              COMMENT 'FK → tj_documents.id',
    kb_id         VARCHAR(32)  NOT NULL              COMMENT 'FK → tj_knowledge_bases.id（冗余）',
    user_id       VARCHAR(50)  NOT NULL              COMMENT '上传者（冗余，权限隔离）',
    chunk_index   INT          NOT NULL              COMMENT '切片序号（从 0 开始）',
    chunk_text    TEXT         NOT NULL              COMMENT '切片文本内容',
    milvus_id     VARCHAR(64)  DEFAULT NULL          COMMENT 'Milvus 中对应的向量 ID',
    token_count   INT          DEFAULT 0             COMMENT 'token 数量（计费用）',
    status        TINYINT      DEFAULT 1             COMMENT '1=正常 0=已删除',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chunks_doc (document_id),
    INDEX idx_chunks_kb (kb_id),
    INDEX idx_chunks_user (user_id),
    INDEX idx_chunks_milvus (milvus_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档切片表';
