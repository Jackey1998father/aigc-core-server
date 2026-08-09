"""
LangGraph 图状态管理

职责：
    1. RAGState TypedDict
    2. 模式常量（MODE_NORMAL / MODE_ENHANCED）+ System Prompts
    3. START 入口路由函数（_route_by_mode）
    4. LangGraph 图构建（build_rag_graph）+ 单例（get_graph）

注：
    - 节点函数（permission_node / retrieval_node / answer_node）放在各自 service 文件
    - 本文件不模块级 import 节点函数，延迟到 build_rag_graph 调用时再 import，
      避免 state.py ↔ model_service.py / permission_service.py 的循环引用

图结构：

                       [START]
                          ↓
                (conditional: _route_by_mode)
                          ↓
        ┌─────────────────┴─────────────────┐
        ↓                                   ↓
   mode == "normal"                  mode == "enhanced"
        ↓                                   ↓
      [END]                         permission_node
                                          ↓
                                   (error → END, 否则 → retrieval)
                                          ↓
                                    retrieval_node
                                          ↓
                                       [END]

注：LLM 流式调用已从 answer_node 移到 rag_chat_service.py，
    图只负责 permission + retrieval，返回 context 后由外层直接 stream LLM
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
    mode: str                             # MODE_NORMAL | MODE_ENHANCED
    kb_ids: List[str]                     # 增强模式要检索的知识库
    query: str
    conversation_id: Optional[str]
    history: List[Dict[str, str]]         # [{role, content}, ...]
    model: Optional[str]
    thinking: bool

    # ===== 中间（仅增强模式会填充）=====
    authorized_kb_ids: List[str]          # 权限过滤后
    authorized_doc_ids: List[str]         # 这些 kb 下的 doc_id
    query_embedding: List[float]
    child_matches: List[Dict[str, Any]]   # Milvus 召回的子块
    reranked_matches: List[Dict[str, Any]]
    parent_chunks: List[Dict[str, Any]]   # 找到的父块
    context: str                          # 拼好的 RAG 上下文（普通模式为空）

    # ===== 输出 =====
    prompt_messages: List[Dict[str, str]]
    error: Optional[str]


# ============================================================
# 2. 模式常量 + System Prompts
# ============================================================
MODE_NORMAL = "normal"        # 普通模式：跳过检索，直接 LLM 回答
MODE_ENHANCED = "enhanced"    # 增强模式：走完整 RAG 流程

# 普通模式：完整 锦点 助手设定
NORMAL_SYSTEM_PROMPT = (
    "你是锦点餐饮管理有限公司的智能助手，专门为公司员工、客户及合作伙伴提供专业、高效的业务咨询服务。"
    "你的主要职责是帮助用户解决与团餐运营、中央厨房管理、餐饮供应链、菜品管理、食品安全、采购配送、客户服务、企业制度等相关的问题。"
    "回答用户问题时，请优先依据公司提供的知识库、业务资料和制度文件进行准确回答；"
    "你需要结合当前对话上下文理解用户意图，但始终以用户最新一条消息为核心，不要机械重复之前已经回答过的内容。"
    "如果用户的问题存在指代不清、信息不足的情况，可以结合历史上下文进行合理推断；"
    "如果仍无法确定，应主动向用户询问必要的信息。"
    "如果用户咨询与锦点餐饮业务无关的问题，请先友好回应用户，再自然引导到锦点餐饮相关服务或业务方向。"
    "回答风格要求：专业、简洁、易懂，像一名熟悉公司业务的内部智能顾问，而不是普通聊天机器人。"
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
# 3. 路由函数（START 入口分发）
# ============================================================
def _route_by_mode(state: RAGState) -> str:
    """
    从 START 出发的条件路由：
        - 增强模式（mode=enhanced 且有 kb_ids） → permission
        - 其他情况 → END（LLM 直接流式回答，不走图内节点）
    """
    if state.get("mode") == MODE_ENHANCED and state.get("kb_ids"):
        return "permission"
    return END


# ============================================================
# 4. 图构建 + 单例
# ============================================================
def build_rag_graph():
    """编译 LangGraph，返回可执行图

    注：节点函数延迟 import，避免 state.py ↔ 其他 service 文件循环引用。
        LLM 流式调用不在此图内，由 rag_chat_service.py 在图返回后直接处理。
    """
    from langgraph.graph import StateGraph, START, END

    from app.services.rag_graph.permission_service import (
        _route_after_permission,
        permission_node,
    )
    from app.services.rag_graph.retrieval_service import retrieval_node

    workflow = StateGraph(RAGState)

    workflow.add_node("permission", permission_node)
    workflow.add_node("retrieval", retrieval_node)

    # 从 START 按 mode 条件分叉
    workflow.add_conditional_edges(
        START,
        _route_by_mode,
        {
            "permission": "permission",  # 增强模式：先进权限
            END: END,                     # 普通模式 / 无 KB：直接结束
        },
    )

    # 增强模式链路：permission → retrieval → END
    workflow.add_conditional_edges(
        "permission",
        _route_after_permission,
        {END: END, "retrieval": "retrieval"},
    )
    workflow.add_edge("retrieval", END)

    return workflow.compile()


# 模块级单例（首次调用时构建一次）
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_rag_graph()
    return _graph
