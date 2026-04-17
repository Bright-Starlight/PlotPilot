"""章节索引服务 - 提供章节摘要 embedding 写入功能

Collection 命名约定：
- Collection 名称：novel_{novel_id}_chunks
- Payload 结构：
  * chapter_number: int - 章节编号
  * text: str - 章节摘要或 Bible 片段
  * kind: str - "chapter_summary" | "bible_snippet"
  * novel_id: str - 小说 ID（冗余但便于跨 collection 查询）
"""
import logging
import uuid
from typing import Optional

from domain.ai.services.embedding_service import EmbeddingService
from domain.ai.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ChapterIndexingService:
    """章节索引服务

    负责将章节摘要和 Bible 片段向量化并写入向量存储。
    使用 novel_id 隔离不同小说的 collection。
    """

    EMBEDDING_DIMENSION = 1536

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService
    ):
        """初始化章节索引服务"""
        self._vector_store = vector_store
        self._embedding_service = embedding_service
        self._embedding_dimension = embedding_service.get_dimension()

    def _get_collection_name(self, novel_id: str) -> str:
        """获取 collection 名称。"""
        return f"novel_{novel_id}_chunks"

    async def ensure_collection(self, novel_id: str) -> None:
        """确保 collection 存在，如果不存在则创建。"""
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.create_collection(
            collection=collection_name,
            dimension=self._embedding_dimension
        )

    async def index_chapter_summary(
        self,
        novel_id: str,
        chapter_number: int,
        summary: str
    ) -> None:
        """索引章节摘要到向量存储。"""
        if not novel_id:
            raise ValueError("novel_id cannot be empty")
        if chapter_number < 1:
            raise ValueError("chapter_number must be >= 1")
        if not summary or not summary.strip():
            raise ValueError("summary cannot be empty")

        await self.ensure_collection(novel_id)
        vector = await self._embedding_service.embed(summary)
        payload = {
            "chapter_number": chapter_number,
            "text": summary,
            "kind": "chapter_summary",
            "novel_id": novel_id
        }
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{novel_id}_ch{chapter_number}_summary"))
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.insert(
            collection=collection_name,
            id=point_id,
            vector=vector,
            payload=payload
        )

    async def index_bible_snippet(
        self,
        novel_id: str,
        chapter_number: int,
        snippet: str,
        snippet_id: Optional[str] = None
    ) -> None:
        """索引 Bible 片段到向量存储。"""
        if not novel_id:
            raise ValueError("novel_id cannot be empty")
        if chapter_number < 1:
            raise ValueError("chapter_number must be >= 1")
        if not snippet or not snippet.strip():
            raise ValueError("snippet cannot be empty")

        await self.ensure_collection(novel_id)
        vector = await self._embedding_service.embed(snippet)
        payload = {
            "chapter_number": chapter_number,
            "text": snippet,
            "kind": "bible_snippet",
            "novel_id": novel_id
        }
        raw_id = f"{novel_id}_ch{chapter_number}_bible_{snippet_id}" if snippet_id else f"{novel_id}_ch{chapter_number}_bible"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, raw_id))
        collection_name = self._get_collection_name(novel_id)
        await self._vector_store.insert(
            collection=collection_name,
            id=point_id,
            vector=vector,
            payload=payload
        )
