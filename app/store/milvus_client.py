"""
Milvus 客户端单例（ProcessLocal + 自动重试）
"""
import os
import threading

from pymilvus import MilvusClient

from app.core.config import settings


class ProcessLocalMilvusClient:
    """
    进程级单例：worker 子进程复用同一个 MilvusClient，自动检测 PID 重建。
    所有方法调用最多 3 次重试（针对连接类错误）。
    """

    def __init__(self, db_name: str, uri: str, token: str = ""):
        self.db_name = db_name
        self.uri = uri
        self.token = token
        self._pid: int | None = None
        self._client: MilvusClient | None = None
        self._lock = threading.Lock()

    def _get_client(self) -> MilvusClient:
        current_pid = os.getpid()
        if self._client is not None and self._pid == current_pid:
            return self._client
        with self._lock:
            if self._client is not None and self._pid == current_pid:
                return self._client
            self._client = MilvusClient(
                db_name=self.db_name,
                uri=self.uri,
                token=self.token or None,
            )
            self._pid = current_pid
            return self._client

    def _reset_client(self) -> MilvusClient:
        with self._lock:
            self._client = MilvusClient(
                db_name=self.db_name,
                uri=self.uri,
                token=self.token or None,
            )
            self._pid = os.getpid()
            return self._client

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "closed channel" in msg
            or "cannot invoke rpc on closed channel" in msg
            or "channel is closed" in msg
            or "channel distribution is not serviceable" in msg
            or "querynode" in msg
        )

    def __getattr__(self, item):
        attr = getattr(self._get_client(), item)
        if not callable(attr):
            return attr

        def _wrapped(*args, **kwargs):
            last_error = None
            for attempt in range(3):
                try:
                    return getattr(self._get_client(), item)(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if self._is_retryable_error(e) and attempt < 2:
                        self._reset_client()
                        continue
                    break
            raise last_error

        return _wrapped


# 全局单例
milvus_client = ProcessLocalMilvusClient(
    db_name=settings.MILVUS_DB_NAME,
    uri=settings.MILVUS_URI,
    token=settings.MILVUS_TOKEN,
)