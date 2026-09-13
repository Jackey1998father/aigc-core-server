"""
LangGraph 图状态管理
"""
import logging
from typing import TypedDict, List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 1. 状态定义
# ============================================================
class RAGState(TypedDict, total=False):
    """RAG 图的统一状态（所有节点共享）"""
    # ===== 输入 =====
    user_id: str
    kb_ids: List[str]                     # 要检索的知识库
    query: str
    conversation_id: Optional[str]
    history: List[Dict[str, str]]         # [{role, content}, ...]
    model: Optional[str]
    thinking: bool
    images: List[str]                     # 图片列表（data URL / http 公网 URL），视觉模型用

    # ===== 中间（仅增强模式会填充）=====
    authorized_kb_ids: List[str]          # 权限过滤后
    authorized_doc_ids: List[str]         # 这些 kb 下的 doc_id
    query_embedding: List[float]
    child_matches: List[Dict[str, Any]]   # Milvus 召回的子块
    reranked_matches: List[Dict[str, Any]]
    parent_chunks: List[Dict[str, Any]]   # 找到的父块
    context: str                          # 拼好的 RAG 上下文（普通模式为空）

    # ===== LLM 流式输出桥接 =====
    on_chunk: Any                         # SSE chunk 回调（外层注入，answer_node 边生成边推送）

    # ===== 输出 =====
    llm_response_text: str                # 最终回答全文（answer_node 填充，用于落库）
    llm_had_error: bool                   # LLM 调用是否出错（answer_node 填充）
    error: Optional[str]


# ============================================================
# 2. System Prompts
# ============================================================
# 普通 prompt：增强模式下检索结果为空时的兜底，也是 /api/v1/chat 普通对话的设定
# （chat_service.py 有自己的普通对话 prompt，此处仅供 answer_node 兜底复用）

NORMAL_SYSTEM_PROMPT = (
    "你是锦点 AI 大模型，是锦点餐饮管理有限公司旗下的智能助手。"
    "你擅长团餐运营、中央厨房管理、菜品管理、餐饮供应链、食品安全、采购配送、客户服务、企业制度等餐饮领域相关问题。"
   
    "\n\n"
    "除了餐饮业务，你也能友好、认真地回答日常生活中的各类问题，帮助用户解决工作、学习、生活等方面的疑问。"
    "回答日常问题时保持专业、清晰、易懂，像一名博学又亲切的助手。"
    "\n\n"
    "你需要结合当前对话上下文理解用户意图，始终以用户最新一条消息为核心，不要机械重复之前已经回答过的内容。"
    "如果用户的问题存在指代不清、信息不足的情况，可以结合历史上下文合理推断；仍无法确定时，主动向用户询问必要信息。"
    "\n\n"
    "安全边界（必须遵守）："
    "如果用户请求涉及游戏、赌博、色情、暴力、违法或其他不当内容，请明确拒绝回答，"
    "并引导用户回到合法、健康、与餐饮业务或日常生活相关的主题。"
)

# 增强模式：分析型 prompt，鼓励深度推理而非照搬资料
ENHANCED_SYSTEM_PROMPT = (
    "你是锦点餐饮管理有限公司的资深业务分析师，擅长从公司内部资料中提炼洞察。\n\n"
    "回答问题时，请遵循以下思维框架：\n\n"
    "1. 理解意图 — 先分析用户真正想解决什么业务问题，而不是只读字面意思；\n"
    "2. 定位信息 — 从【参考资料】中找出所有相关片段，注意不同文档之间的关联、互补和矛盾；\n"
    "3. 分析加工 — 不只是罗列事实，要说明这些信息意味着什么、对业务有什么影响、有无风险或机会；\n"
    "4. 诚实边界 — 如果资料中某方面信息不全或数据过时，请明确指出「参考资料中未涉及该部分」；\n"
    "5. 可执行建议 — 在资料支持的前提下，给出下一步行动建议或需要关注的方向。\n\n"
    "约束：所有判断必须有【参考资料】依据，不得凭空编造。如果资料不足以支撑深入分析，"
    "请如实告知哪些部分缺少信息，而不是强凑答案。\n\n"
    "回答风格：像一位熟悉业务的顾问在跟同事沟通——专业但不僵硬，有观点但不武断。"
)


# ============================================================
# 3. 图构建 + 单例
# ============================================================
def build_rag_graph():
    """编译 LangGraph，返回可执行图

    固定链路：START → permission → retrieval → answer → END
    （permission 校验失败时直接 END，错误信息由外层兜底输出）

    注：节点函数延迟 import，避免 state.py ↔ 其他 service 文件循环引用。
        answer_node 在图内完成 LLM 流式调用（通过 state["on_chunk"] 回调
        实时推送 SSE chunk），外层 rag_chat_service.py 只做队列桥接。
    """
    from langgraph.graph import StateGraph, START, END

    from app.services.rag_graph.permission_service import (
        _route_after_permission,
        permission_node,
    )
    from app.services.rag_graph.retrieval_service import retrieval_node
    from app.services.rag_graph.model_service import answer_node

    workflow = StateGraph(RAGState)

    workflow.add_node("permission", permission_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("answer", answer_node)

    # 固定链路：START → permission → retrieval → answer → END
    workflow.add_edge(START, "permission")
    workflow.add_conditional_edges(
        "permission",
        _route_after_permission,
        {END: END, "retrieval": "retrieval"},
    )
    workflow.add_edge("retrieval", "answer")
    workflow.add_edge("answer", END)

    return workflow.compile()


# 模块级单例（首次调用时构建一次）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_rag_graph()
    return _graph
