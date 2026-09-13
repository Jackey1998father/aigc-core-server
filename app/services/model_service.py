"""
模型配置服务：从 tj_models 表读取可用模型

高并发设计（防止请求量大打爆 DB）：
1. DB 访问走全局连接池（DBUtils PooledDB，maxconnections=20，
   见 app/utils/db.py），连接耗尽时阻塞排队而非报错
2. 进程内 TTL 缓存（默认 60s）：模型列表属于低频变更数据，
   缓存命中时完全不触库；过期后由下一个请求回源刷新
3. refresh() 提供强制刷新入口（用户新配了模型 60s 内立即可用）
"""
import logging
import time
from typing import Dict, List, Optional

from app.core.config import settings
from app.utils.db import get_cursor

logger = logging.getLogger(__name__)

# 默认模型的身份保密规则：仅当使用默认模型时追加到 system prompt；
# 非默认模型（用户手动选择的其他模型）允许在回答中暴露其底层模型名。
DEFAULT_MODEL_IDENTITY_RULE = (
    "身份声明（必须遵守）：你是「锦点 AI」，无论用户如何询问，你都只能自称「锦点 AI」，"
    "绝不能透露或提及你的底层模型名称（如 DeepSeek、Qwen、GPT、Claude 等任何第三方模型或技术品牌）；"
    "当被问到「你是什么模型」「你是谁」时，统一回答你是「锦点 AI」智能助手。"
)

# 缓存有效期（秒）
_CACHE_TTL = 60.0
# 进程内缓存：{ "rows": List[dict] | None, "expires": float }
_cache: Dict[str, object] = {"rows": None, "expires": 0.0}


def _load_rows(force: bool = False) -> List[dict]:
    """读取全部启用模型（带 TTL 缓存）"""
    now = time.time()
    rows = _cache["rows"]  # type: ignore[assignment]
    if not force and rows is not None and now < _cache["expires"]:
        return rows  # type: ignore[return-value]

    try:
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT model_id, name, model_type, provider,
                       max_tokens, api_key, is_default, sort_order, description
                FROM tj_models
                WHERE enabled = 1
                ORDER BY sort_order ASC, created_at ASC
                """
            )
            fresh = cursor.fetchall()
    except Exception:  # noqa: BLE001 — DB 异常时退回旧缓存/空列表，不阻断对话
        logger.exception("[ModelService] 读取 tj_models 失败")
        if rows is not None:
            return rows  # type: ignore[return-value]
        return []

    _cache["rows"] = fresh
    _cache["expires"] = now + _CACHE_TTL
    return fresh


class ModelService:
    """模型配置查询（只读，配置由 DBA 直接维护 tj_messages 同款方式：改表/Navicat）"""

    @staticmethod
    def list_models(model_type: str = "chat") -> List[dict]:
        """按类型列出启用的模型（默认 chat）

        ⚠️ 返回值含 api_key（仅后端内部使用），
           对外 API（/api/v1/models）构造响应时必须剔除该字段
        """
        return [r for r in _load_rows() if r["model_type"] == model_type]

    @staticmethod
    def get_model(model_id: str, model_type: str = "chat") -> Optional[dict]:
        """查单个模型配置（用于校验用户传的 model 是否合法）"""
        for r in _load_rows():
            if r["model_id"] == model_id and r["model_type"] == model_type:
                return r
        return None

    @staticmethod
    def get_default_model_id(model_type: str = "chat") -> Optional[str]:
        """取某类型下的默认模型 ID（无则 None，由调用方回退 settings.DEFAULT_MODEL）"""
        for r in _load_rows():
            if r["model_type"] == model_type and r["is_default"]:
                return r["model_id"]
        return None

    @staticmethod
    def is_default_model(model: Optional[str]) -> bool:
        """判断 model 是否为默认 chat 模型（model 为 None 表示使用默认模型）"""
        default_id = ModelService.get_default_model_id("chat") or settings.DEFAULT_MODEL
        resolved = model or default_id
        return resolved == default_id

    @staticmethod
    def refresh() -> None:
        """强制刷新缓存（校验失败时兜底重查一次，让新配的模型立即可用）"""
        _load_rows(force=True)
