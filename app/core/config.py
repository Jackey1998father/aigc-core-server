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
    DEFAULT_MODEL: str = "zai-org/GLM-5.2"
    DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    DEFAULT_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    # 如需要固定 API Key（不依赖请求头传入），可在这里配置
    SILICON_FLOW_API_KEY: str = "sk-lbaejguljpqjckzkqtaybqnjxzzjizfqyijkxfwatbxrglnv"

    # ===== Milvus 配置 =====
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "documents"
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # ===== 服务配置 =====
    # 本服务的 base URL，用于内部服务调用
    SERVER_BASE_URL: str = "http://106.14.181.222:8000"

    # ===== MySQL 配置 =====
    MYSQL_HOST: str = ""
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = ""

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
