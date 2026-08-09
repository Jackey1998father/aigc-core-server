-- ============================================
-- AIGC 知识库 & 文档表
-- 数据库：aigc
-- 说明：
--   1. 每个用户只能看到自己的知识库和文档（user_id 隔离）
--   2. 后期可扩展管理员角色查看全部
--   3. 文档解析状态预留 parse_status 字段（后续对接 MinerU）
-- ============================================

-- 知识库表
CREATE TABLE IF NOT EXISTS tj_knowledge_bases (
    id           VARCHAR(32)  NOT NULL PRIMARY KEY   COMMENT 'UUID hex',
    user_id      VARCHAR(50)  NOT NULL               COMMENT '所有者 user_id → aigc_users.user_id',
    name         VARCHAR(100) NOT NULL               COMMENT '知识库名称',
    description  VARCHAR(500) DEFAULT ''             COMMENT '描述',
    status       TINYINT      DEFAULT 1              COMMENT '1=正常 0=已删除（软删除）',
    created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_kb_user_id (user_id),
    INDEX idx_kb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库表';


-- 文档表
CREATE TABLE IF NOT EXISTS tj_documents (
    id            VARCHAR(32)  NOT NULL PRIMARY KEY  COMMENT 'UUID hex',
    kb_id         VARCHAR(32)  NOT NULL              COMMENT '所属知识库 → tj_knowledge_bases.id',
    user_id       VARCHAR(50)  NOT NULL              COMMENT '上传者 user_id（冗余，便于权限隔离查询）',
    title         VARCHAR(255) NOT NULL              COMMENT '文档标题（原始文件名，不含扩展名）',
    file_name     VARCHAR(255) NOT NULL              COMMENT '用户上传的原始文件名（含扩展名）',
    file_type     VARCHAR(20)  NOT NULL              COMMENT '文件类型：pdf/txt/ppt/pptx/doc/docx/csv/xlsx',
    file_size     BIGINT       DEFAULT 0             COMMENT '文件大小（字节）',
    minio_path    VARCHAR(500) NOT NULL              COMMENT 'RustFS 对象存储路径',
    content_text  LONGTEXT     DEFAULT NULL          COMMENT '解析后的文本内容（MinerU 解析结果，后续填充）',
    parse_status  TINYINT      DEFAULT 0             COMMENT '解析状态：0=待解析 1=解析中 2=已完成 3=失败',
    status        TINYINT      DEFAULT 1             COMMENT '1=正常 0=已删除（软删除）',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doc_kb_id (kb_id),
    INDEX idx_doc_user_id (user_id),
    INDEX idx_doc_parse_status (parse_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表';

