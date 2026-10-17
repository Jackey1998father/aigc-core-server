import logging

from app.core.config import settings


def setup_logging() -> None:
    """配置根 logger，让各模块 `logging.getLogger(__name__)` 的日志正常输出到控制台。

    不调用时，根 logger 保持 Python 默认（level=WARNING 且无 handler），
    模块里的 logger.info 会被静默丢弃——这就是看不到 [rag.retrieval.top5] 等日志的原因。
    """
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def get_logger(name: str = "app"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger