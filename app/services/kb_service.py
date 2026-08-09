"""
知识库服务
"""
import uuid
from typing import List

from app.utils.db import get_cursor
from app.schemas.kb import KnowledgeBaseItem


class KnowledgeBaseService:
    """知识库 CRUD"""

    @staticmethod
    def create(user_id: str, name: str, description: str = "") -> KnowledgeBaseItem:
        """创建知识库"""
        kb_id = uuid.uuid4().hex
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO tj_knowledge_bases (id, user_id, name, description) VALUES (%s, %s, %s, %s)",
                (kb_id, user_id, name, description),
            )
        return KnowledgeBaseItem(
            id=kb_id,
            name=name,
            description=description,
            doc_count=0,
        )

    @staticmethod
    def list_by_user(user_id: str) -> List[KnowledgeBaseItem]:
        """获取当前用户的所有知识库（按 updated_at 倒序，附带文档数量）"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    k.id, k.name, k.description, k.created_at, k.updated_at,
                    COUNT(d.id) AS doc_count
                FROM tj_knowledge_bases k
                LEFT JOIN tj_documents d ON d.kb_id = k.id AND d.status = 1
                WHERE k.user_id = %s AND k.status = 1
                GROUP BY k.id
                ORDER BY k.updated_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()

        return [
            KnowledgeBaseItem(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                doc_count=row["doc_count"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    @staticmethod
    def get_by_id(kb_id: str, user_id: str) -> KnowledgeBaseItem | None:
        """获取单个知识库详情（校验归属权限）"""
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    k.id, k.name, k.description, k.created_at, k.updated_at,
                    COUNT(d.id) AS doc_count
                FROM tj_knowledge_bases k
                LEFT JOIN tj_documents d ON d.kb_id = k.id AND d.status = 1
                WHERE k.id = %s AND k.user_id = %s AND k.status = 1
                GROUP BY k.id
                """,
                (kb_id, user_id),
            )
            row = cursor.fetchone()

        if not row:
            return None

        return KnowledgeBaseItem(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            doc_count=row["doc_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def update(kb_id: str, user_id: str, name: str | None = None, description: str | None = None) -> bool:
        """更新知识库名称/描述（校验归属权限）"""
        fields = []
        values = []
        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if description is not None:
            fields.append("description = %s")
            values.append(description)
        if not fields:
            return True  # 没有更新字段，不报错

        values.extend([kb_id, user_id])
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE tj_knowledge_bases SET {', '.join(fields)} WHERE id = %s AND user_id = %s AND status = 1",
                values,
            )
            return cursor.rowcount > 0

    @staticmethod
    def delete(kb_id: str, user_id: str) -> bool:
        """
        软删除知识库（同时软删除其下所有文档）。
        校验 user_id 防止越权。
        """
        with get_cursor(commit=True) as cursor:
            # 软删除知识库
            cursor.execute(
                "UPDATE tj_knowledge_bases SET status = 0 WHERE id = %s AND user_id = %s AND status = 1",
                (kb_id, user_id),
            )
            if cursor.rowcount == 0:
                return False
            # 级联软删除文档
            cursor.execute(
                "UPDATE tj_documents SET status = 0 WHERE kb_id = %s AND status = 1",
                (kb_id,),
            )
            return True
