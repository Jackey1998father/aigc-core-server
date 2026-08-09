from typing import List
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 根据 APP_ENV 自动选择配置文件（本地默认 development，Docker 中设为 production）
_APP_ENV = os.getenv("APP_ENV", "development")
_ENV_FILE = _PROJECT_ROOT / f".env.{_APP_ENV}"


class Settings(BaseSettings):
    APP_ENV: str = "development"


class Settings(BaseSettings):
    PROJECT_NAME: str = "AIGC Core Server"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = True

    # ===== 服务器配置 =====
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ===== CORS 配置 =====
    CORS_ORIGINS: str = "*"
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: str = "*"
    CORS_HEADERS: str = "*"

    # ===== 安全配置 =====
    # 接口鉴用的 Bearer Token，留空则不校验（不推荐生产环境）
    API_SECRET_TOKEN: str = ""
    # 用于签名等场景的密钥
    SECRET_KEY: str = "change-me-please-in-production"

    # ===== 日志配置 =====
    LOG_LEVEL: str = "info"
    LOG_FILE: str = ""

    # ===== 限流配置 =====
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_ENABLED: bool = False

    # ===== 上游模型服务配置 =====
    SILICON_FLOW_URL: str = "https://api.siliconflow.cn/v1/chat/completions"
    SILICON_FLOW_EMBEDDING_URL: str = "https://api.siliconflow.cn/v1/embeddings"
    SILICON_FLOW_RERANK_URL: str = "https://api.siliconflow.cn/v1/rerank"
    DEFAULT_MODEL: str = "deepseek-ai/DeepSeek-V4-Flash"
    DEFAULT_MAX_TOKENS: int = 8192  # LLM 最大输出 token 数（思考模式下推理 token 也从中扣除）
    DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    DEFAULT_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    # 如需要固定 API Key（不依赖请求头传入），可在这里配置
    SILICON_FLOW_API_KEY: str = "sk-lbaejguljpqjckzkqtaybqnjxzzjizfqyijkxfwatbxrglnv"

    # ===== Milvus 配置 =====
    MILVUS_HOST: str = "106.14.181.222"
    MILVUS_PORT: int = 19530
    MILVUS_DB_NAME: str = "aigc_rag_milvus"
    MILVUS_URI: str = f"http://{MILVUS_HOST}:{MILVUS_PORT}"
    MILVUS_TOKEN: str = ""
    # 三个 collection（parent / child 纯文本 / child 带向量）
    MILVUS_PARENT_COLLECTION: str = "aigc_parent_docs"
    MILVUS_CHILD_COLLECTION: str = "aigc_child_docs"
    MILVUS_BGE_COLLECTION: str = "aigc_docs_bge"
    # BGE 向量维度（需与 embedding 模型一致）
    MILVUS_BGE_DIM: int = 1024
    # 用户名密码（占位，当前用无认证模式）
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # ===== 服务配置 =====
    # 本服务的 base URL，用于内部服务调用
    SERVER_BASE_URL: str = "http://106.14.181.222:8000"

    # ===== RustFS / MinIO 配置（S3 兼容对象存储）=====
    RUSTFS_ADDRESS: str = "106.14.181.222"
    RUSTFS_PORT: int = 9000
    RUSTFS_ACCESS_KEY_ID: str = "rustfsadmin"
    RUSTFS_SECRET_ACCESS_KEY: str = "rustfsadmin"
    RUSTFS_USE_SSL: bool = False
    RUSTFS_BUCKET_NAME: str = "agent-user-files"
    RUSTFS_ROOT_PATH: str = "files"
    RUSTFS_REGION: str = "us-east-1"

    # ===== MySQL 配置 =====
    MYSQL_HOST: str = ""
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = ""

    # ===== Redis / Celery 配置 =====
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # ===== 文档解析配置 =====
    # 轻量解析直接在 Worker 进程里完成，不需要外部服务
    # 如需启用 PaddleOCR（扫描件/图片），见 app/tasks/__init__.py

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_method_list(self) -> List[str]:
        if self.CORS_METHODS.strip() == "*":
            return ["*"]
        return [m.strip().upper() for m in self.CORS_METHODS.split(",") if m.strip()]

    @property
    def cors_header_list(self) -> List[str]:
        if self.CORS_HEADERS.strip() == "*":
            return ["*"]
        return [h.strip() for h in self.CORS_HEADERS.split(",") if h.strip()]


settings = Settings()
