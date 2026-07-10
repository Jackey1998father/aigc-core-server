"""
会话 & 消息持久化服务
"""
import uuid
from typing import List

from app.utils.db import get_cursor
from app.schemas.conversation import ConversationItem, MessageItem


class ConversationService:
    """会话管理"""

    @staticmethod
    def list_by_user(user_id: str) -> List[ConversationItem]:
        """获取当前用户的所有会话列表（按 updated_at 倒序，附带 message_count）"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    c.id, c.title, c.created_at, c.updated_at,
                    COUNT(m.id) AS message_count
                FROM tj_conversations c
                LEFT JOIN tj_messages m ON m.conversation_id = c.id
                WHERE c.user_id = %s
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        return [
            ConversationItem(
                id=row["id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                message_count=row["message_count"],
            )
            for row in rows
        ]

    @staticmethod
    def create(user_id: str, title: str = "新对话") -> ConversationItem:
        """创建新会话"""
        conv_id = uuid.uuid4().hex
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO tj_conversations (id, user_id, title) VALUES (%s, %s, %s)",
                (conv_id, user_id, title),
            )

        return ConversationItem(
            id=conv_id,
            title=title,
            created_at=None,   # 由 DB DEFAULT CURRENT_TIMESTAMP 生成
            updated_at=None,
            message_count=0,
        )

    @staticmethod
    def ensure_exists(conv_id: str, user_id: str, title: str = "新对话") -> str:
        """
        确保会话存在：存在且属于当前用户则直接返回 ID，
        不存在则自动创建并返回新 ID。
        """
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id FROM tj_conversations WHERE id = %s AND user_id = %s",
                (conv_id, user_id),
            )
            if cursor.fetchone():
                return conv_id  # 已存在，直接返回

        # 不存在则创建
        ConversationService.create(user_id, title)
        return conv_id

    @staticmethod
    def delete(conv_id: str, user_id: str) -> bool:
        """
        删除会话（CASCADE 自动删除关联消息）。
        校验 user_id 防止越权删除。
        """
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM tj_conversations WHERE id = %s AND user_id = %s",
                (conv_id, user_id),
            )
            return cursor.rowcount > 0

    @staticmethod
    def update_title(conv_id: str, user_id: str, title: str):
        """更新会话标题"""
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE tj_conversations SET title = %s WHERE id = %s AND user_id = %s",
                (title, conv_id, user_id),
            )


class MessageService:
    """消息管理"""

    @staticmethod
    def save(conversation_id: str, role: str, content: str) -> str:
        """保存一条消息，返回消息 ID"""
        msg_id = uuid.uuid4().hex
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO tj_messages (id, conversation_id, role, content) VALUES (%s, %s, %s, %s)",
                (msg_id, conversation_id, role, content),
            )
        return msg_id

    @staticmethod
    def get_by_conversation(conversation_id: str, user_id: str, limit: int = 20) -> List[MessageItem]:
        """
        获取指定会话的消息列表（按时间升序），最多取 limit 条。
        校验 user_id 防止越权访问。
        """
        with get_cursor() as cursor:
            # 先校验会话归属
            cursor.execute(
                "SELECT id FROM tj_conversations WHERE id = %s AND user_id = %s",
                (conversation_id, user_id),
            )
            if not cursor.fetchone():
                return []

            cursor.execute(
                """
                SELECT id, role, content, created_at
                FROM tj_messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (conversation_id, limit),
            )
            rows = cursor.fetchall()
            # 数据库按倒序取最新 limit 条，再反转回时间升序
            rows = list(reversed(rows))

        return [
            MessageItem(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
