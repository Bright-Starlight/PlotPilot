"""
故事结构节点 Repository
"""

import sqlite3
import json
from typing import List, Optional
from datetime import datetime

from domain.structure.story_node import StoryNode, NodeType, StoryTree, PlanningStatus, PlanningSource


class StoryNodeRepository:
    """故事结构节点仓储"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_sync(self, node: StoryNode) -> StoryNode:
        """同步保存（供 NovelService 等非 async 调用链使用）。"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO story_nodes (
                    id, novel_id, parent_id, node_type, number, title, description, order_index,
                    planning_status, planning_source,
                    chapter_start, chapter_end, chapter_count, suggested_chapter_count,
                    content, outline, word_count, status,
                    themes, key_events, narrative_arc, conflicts,
                    pov_character_id, timeline_start, timeline_end,
                    metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.id,
                node.novel_id,
                node.parent_id,
                node.node_type.value,
                node.number,
                node.title,
                node.description,
                node.order_index,
                node.planning_status.value,
                node.planning_source.value,
                node.chapter_start,
                node.chapter_end,
                node.chapter_count,
                node.suggested_chapter_count,
                node.content,
                node.outline,
                node.word_count,
                node.status,
                json.dumps(node.themes),
                json.dumps(node.key_events),
                node.narrative_arc,
                json.dumps(node.conflicts),
                node.pov_character_id,
                node.timeline_start,
                node.timeline_end,
                json.dumps(node.metadata),
                node.created_at.isoformat(),
                node.updated_at.isoformat(),
            ))
            conn.commit()
            return node
        finally:
            conn.close()

    async def save(self, node: StoryNode) -> StoryNode:
        """保存节点"""
        return self.save_sync(node)

    async def update(self, node: StoryNode) -> StoryNode:
        """更新节点"""
        node.updated_at = datetime.now()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE story_nodes SET
                    parent_id = ?,
                    node_type = ?,
                    number = ?,
                    title = ?,
                    description = ?,
                    order_index = ?,
                    planning_status = ?,
                    planning_source = ?,
                    chapter_start = ?,
                    chapter_end = ?,
                    chapter_count = ?,
                    suggested_chapter_count = ?,
                    content = ?,
                    outline = ?,
                    word_count = ?,
                    status = ?,
                    themes = ?,
                    key_events = ?,
                    narrative_arc = ?,
                    conflicts = ?,
                    pov_character_id = ?,
                    timeline_start = ?,
                    timeline_end = ?,
                    metadata = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                node.parent_id,
                node.node_type.value,
                node.number,
                node.title,
                node.description,
                node.order_index,
                node.planning_status.value,
                node.planning_source.value,
                node.chapter_start,
                node.chapter_end,
                node.chapter_count,
                node.suggested_chapter_count,
                node.content,
                node.outline,
                node.word_count,
                node.status,
                json.dumps(node.themes),
                json.dumps(node.key_events),
                node.narrative_arc,
                json.dumps(node.conflicts),
                node.pov_character_id,
                node.timeline_start,
                node.timeline_end,
                json.dumps(node.metadata),
                node.updated_at.isoformat(),
                node.id,
            ))
            conn.commit()
            return node
        finally:
            conn.close()

    async def save_batch(self, nodes: List[StoryNode]) -> List[StoryNode]:
        """批量保存节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for node in nodes:
                cursor.execute("""
                    INSERT OR REPLACE INTO story_nodes (
                        id, novel_id, parent_id, node_type, number, title, description, order_index,
                        planning_status, planning_source,
                        chapter_start, chapter_end, chapter_count, suggested_chapter_count,
                        content, outline, word_count, status,
                        themes, key_events, narrative_arc, conflicts,
                        pov_character_id, timeline_start, timeline_end,
                        metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.id,
                    node.novel_id,
                    node.parent_id,
                    node.node_type.value,
                    node.number,
                    node.title,
                    node.description,
                    node.order_index,
                    node.planning_status.value,
                    node.planning_source.value,
                    node.chapter_start,
                    node.chapter_end,
                    node.chapter_count,
                    node.suggested_chapter_count,
                    node.content,
                    node.outline,
                    node.word_count,
                    node.status,
                    json.dumps(node.themes),
                    json.dumps(node.key_events),
                    node.narrative_arc,
                    json.dumps(node.conflicts),
                    node.pov_character_id,
                    node.timeline_start,
                    node.timeline_end,
                    json.dumps(node.metadata),
                    node.created_at.isoformat(),
                    node.updated_at.isoformat(),
                ))
            conn.commit()
            return nodes
        finally:
            conn.close()

    async def get_by_id(self, node_id: str) -> Optional[StoryNode]:
        """根据 ID 获取节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM story_nodes WHERE id = ?", (node_id,))
            row = cursor.fetchone()
            return self._row_to_entity(row) if row else None
        finally:
            conn.close()

    def get_by_novel_sync(self, novel_id: str) -> List[StoryNode]:
        """同步列出某小说的全部结构节点。"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE novel_id = ?
                ORDER BY order_index
            """, (novel_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            conn.close()

    async def get_by_novel(self, novel_id: str) -> List[StoryNode]:
        """获取小说的所有节点"""
        return self.get_by_novel_sync(novel_id)

    def get_tree_sync(self, novel_id: str) -> StoryTree:
        """同步获取结构树（供 NovelService 使用）。"""
        return StoryTree(novel_id=novel_id, nodes=self.get_by_novel_sync(novel_id))

    async def get_tree(self, novel_id: str) -> StoryTree:
        """获取小说的结构树"""
        return self.get_tree_sync(novel_id)

    def get_children_sync(self, parent_id: str) -> List[StoryNode]:
        """同步获取子节点。"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE parent_id = ?
                ORDER BY order_index
            """, (parent_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            conn.close()

    async def get_children(self, parent_id: str) -> List[StoryNode]:
        """获取子节点"""
        return self.get_children_sync(parent_id)

    async def get_chapters_by_novel(self, novel_id: str) -> List[StoryNode]:
        """获取小说的所有章节"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE novel_id = ? AND node_type = 'chapter'
                ORDER BY order_index
            """, (novel_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            conn.close()

    async def delete(self, node_id: str) -> bool:
        """删除节点（级联删除子节点）"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM story_nodes WHERE id = ?", (node_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def delete_by_novel(self, novel_id: str) -> int:
        """删除小说的所有节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM story_nodes WHERE novel_id = ?", (novel_id,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> StoryNode:
        """将数据库行转换为实体"""
        # sqlite3.Row 不支持 .get() 方法，需要先转换为字典
        row_dict = dict(row)

        return StoryNode(
            id=row_dict["id"],
            novel_id=row_dict["novel_id"],
            parent_id=row_dict["parent_id"],
            node_type=NodeType(row_dict["node_type"]),
            number=row_dict["number"],
            title=row_dict["title"],
            description=row_dict["description"],
            order_index=row_dict["order_index"],

            planning_status=PlanningStatus(row_dict.get("planning_status", "draft")),
            planning_source=PlanningSource(row_dict.get("planning_source", "manual")),

            chapter_start=row_dict["chapter_start"],
            chapter_end=row_dict["chapter_end"],
            chapter_count=row_dict["chapter_count"],
            suggested_chapter_count=row_dict.get("suggested_chapter_count"),

            content=row_dict["content"],
            outline=row_dict.get("outline"),
            word_count=row_dict["word_count"],
            status=row_dict["status"],

            themes=row_dict.get("themes", "[]"),
            key_events=row_dict.get("key_events", "[]"),
            narrative_arc=row_dict.get("narrative_arc"),
            conflicts=row_dict.get("conflicts", "[]"),

            pov_character_id=row_dict.get("pov_character_id"),
            timeline_start=row_dict.get("timeline_start"),
            timeline_end=row_dict.get("timeline_end"),

            metadata=row_dict.get("metadata", "{}"),

            created_at=datetime.fromisoformat(row_dict["created_at"]),
            updated_at=datetime.fromisoformat(row_dict["updated_at"]),
        )
