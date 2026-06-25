from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DEFAULT_MODEL: str = "Pro/zai-org/GLM-5.1"
    DEFAULT_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    DEFAULT_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    # 如需要固定 API Key（不依赖请求头传入），可在这里配置
    SILICON_FLOW_API_KEY: str = ""

    # ===== Milvus 配置 =====
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "documents"
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # ===== 服务配置 =====
    # 本服务的 base URL，用于内部服务调用
    SERVER_BASE_URL: str = "http://106.14.181.222:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
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
