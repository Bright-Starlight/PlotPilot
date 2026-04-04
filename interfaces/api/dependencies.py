"""依赖注入配置

提供 FastAPI 依赖注入函数，用于创建服务和仓储实例。
"""
import logging
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

from application.paths import DATA_DIR
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.repositories.file_novel_repository import FileNovelRepository
from infrastructure.persistence.repositories.file_chapter_repository import FileChapterRepository
from infrastructure.persistence.repositories.file_bible_repository import FileBibleRepository
from infrastructure.persistence.repositories.file_cast_repository import FileCastRepository
from infrastructure.persistence.repositories.file_knowledge_repository import FileKnowledgeRepository
from infrastructure.persistence.repositories.file_storyline_repository import FileStorylineRepository
from infrastructure.persistence.repositories.file_plot_arc_repository import FilePlotArcRepository
from infrastructure.persistence.repositories.file_foreshadowing_repository import FileForeshadowingRepository
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.config.settings import Settings

from application.services.novel_service import NovelService
from application.services.chapter_service import ChapterService
from application.services.bible_service import BibleService
from application.services.cast_service import CastService
from application.services.knowledge_service import KnowledgeService
from application.services.context_builder import ContextBuilder
from application.services.auto_bible_generator import AutoBibleGenerator
from application.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.services.state_extractor import StateExtractor
from application.services.state_updater import StateUpdater
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.services.hosted_write_service import HostedWriteService
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.bible.services.relationship_engine import RelationshipEngine
from domain.ai.services.vector_store import VectorStore


logger = logging.getLogger(__name__)

# 全局存储实例
_storage = None


def _anthropic_api_key() -> Optional[str]:
    """优先 ANTHROPIC_API_KEY，否则 ANTHROPIC_AUTH_TOKEN（与部分代理/IDE 配置命名一致）。"""
    raw = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if raw is None:
        return None
    key = raw.strip()
    return key or None


def _anthropic_base_url() -> Optional[str]:
    u = os.getenv("ANTHROPIC_BASE_URL")
    return u.strip() if u and u.strip() else None


def _anthropic_settings(require_key: bool = True) -> Optional[Settings]:
    """构建 Anthropic Settings；require_key=False 时无密钥返回 None。"""
    key = _anthropic_api_key()
    if not key:
        if require_key:
            raise ValueError(
                "Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN (optional: ANTHROPIC_BASE_URL)"
            )
        return None
    return Settings(api_key=key, base_url=_anthropic_base_url())


def get_storage() -> FileStorage:
    """获取存储后端实例

    Returns:
        FileStorage 实例
    """
    global _storage
    if _storage is None:
        _storage = FileStorage(DATA_DIR)
    return _storage


# Repository 依赖
def get_novel_repository() -> SqliteNovelRepository:
    """获取 Novel 仓储（SQLite）

    Returns:
        SqliteNovelRepository 实例
    """
    return SqliteNovelRepository(get_database())


def get_chapter_repository() -> SqliteChapterRepository:
    """获取 Chapter 仓储（SQLite）

    Returns:
        SqliteChapterRepository 实例
    """
    return SqliteChapterRepository(get_database())


def get_bible_repository() -> FileBibleRepository:
    """获取 Bible 仓储

    Returns:
        FileBibleRepository 实例
    """
    return FileBibleRepository(get_storage())


def get_cast_repository() -> FileCastRepository:
    """获取 Cast 仓储

    Returns:
        FileCastRepository 实例
    """
    return FileCastRepository(get_storage())


def get_knowledge_repository() -> SqliteKnowledgeRepository:
    """获取 Knowledge 仓储（SQLite）

    Returns:
        SqliteKnowledgeRepository 实例
    """
    return SqliteKnowledgeRepository(get_database())


def get_storyline_repository() -> FileStorylineRepository:
    """获取 Storyline 仓储

    Returns:
        FileStorylineRepository 实例
    """
    return FileStorylineRepository(get_storage())


def get_plot_arc_repository() -> FilePlotArcRepository:
    """获取 PlotArc 仓储

    Returns:
        FilePlotArcRepository 实例
    """
    return FilePlotArcRepository(get_storage())


def get_foreshadowing_repository():
    """获取 Foreshadowing 仓储

    Returns:
        FileForeshadowingRepository 实例
    """
    return FileForeshadowingRepository(get_storage())


def get_story_node_repository() -> StoryNodeRepository:
    """获取 StoryNode 仓储

    Returns:
        StoryNodeRepository 实例
    """
    db_path = str(DATA_DIR / "aitext.db")
    return StoryNodeRepository(db_path)


# Service 依赖
def get_novel_service() -> NovelService:
    """获取 Novel 服务

    Returns:
        NovelService 实例
    """
    return NovelService(
        get_novel_repository(),
        get_chapter_repository(),
        get_story_node_repository()
    )


def get_chapter_service() -> ChapterService:
    """获取 Chapter 服务

    Returns:
        ChapterService 实例
    """
    return ChapterService(get_chapter_repository(), get_novel_repository())


def get_hosted_write_service() -> HostedWriteService:
    """托管连写：自动大纲 + 多章流式生成 + 可选落库。"""
    return HostedWriteService(get_auto_workflow(), get_chapter_service(), get_novel_service())


def get_bible_service() -> BibleService:
    """获取 Bible 服务

    Returns:
        BibleService 实例
    """
    from application.paths import get_db_path
    from application.services.bible_location_triple_sync import BibleLocationTripleSyncService
    from infrastructure.persistence.database.triple_repository import TripleRepository

    sync = BibleLocationTripleSyncService(TripleRepository(get_db_path()))
    return BibleService(get_bible_repository(), location_triple_sync=sync)


def get_cast_service() -> CastService:
    """获取 Cast 服务

    Returns:
        CastService 实例
    """
    storage = get_storage()
    storage_root = storage.base_path
    return CastService(storage_root, knowledge_repository=get_knowledge_repository())


def get_knowledge_service() -> KnowledgeService:
    """获取 Knowledge 服务

    Returns:
        KnowledgeService 实例
    """
    return KnowledgeService(get_knowledge_repository())


def get_storyline_manager() -> StorylineManager:
    """获取 Storyline 管理器

    Returns:
        StorylineManager 实例
    """
    return StorylineManager(get_storyline_repository())


def get_consistency_checker() -> ConsistencyChecker:
    """获取一致性检查器

    Returns:
        ConsistencyChecker 实例
    """
    return ConsistencyChecker()


def get_vector_store() -> VectorStore:
    """获取向量存储（简化实现）

    Returns:
        VectorStore 实例（Mock）
    """
    # 简化实现：返回 None，实际应该返回真实的向量存储
    # 在测试和开发中可以使用 Mock
    return None


def get_relationship_engine() -> RelationshipEngine:
    """获取关系引擎

    Returns:
        RelationshipEngine 实例
    """
    from domain.bible.value_objects.relationship_graph import RelationshipGraph
    return RelationshipEngine(RelationshipGraph())


def get_context_builder() -> ContextBuilder:
    """获取上下文构建器

    Returns:
        ContextBuilder 实例
    """
    return ContextBuilder(
        bible_service=get_bible_service(),
        storyline_manager=get_storyline_manager(),
        relationship_engine=get_relationship_engine(),
        vector_store=get_vector_store(),
        novel_repository=get_novel_repository(),
        chapter_repository=get_chapter_repository()
    )


def get_auto_workflow() -> AutoNovelGenerationWorkflow:
    """获取自动小说生成工作流

    Returns:
        AutoNovelGenerationWorkflow 实例
    """
    settings = _anthropic_settings(require_key=False)
    if settings:
        llm_service = AnthropicProvider(settings)
        logger.info("Using AnthropicProvider for workflow")
    else:
        from infrastructure.ai.providers.mock_provider import MockProvider
        llm_service = MockProvider()
        logger.warning("No API key found, using MockProvider for workflow")

    return AutoNovelGenerationWorkflow(
        context_builder=get_context_builder(),
        consistency_checker=get_consistency_checker(),
        storyline_manager=get_storyline_manager(),
        plot_arc_repository=get_plot_arc_repository(),
        llm_service=llm_service,
        state_extractor=get_state_extractor(),
        state_updater=get_state_updater(),
        bible_repository=get_bible_repository(),
        foreshadowing_repository=get_foreshadowing_repository()
    )


def get_auto_bible_generator() -> AutoBibleGenerator:
    """获取自动 Bible 生成器

    Returns:
        AutoBibleGenerator 实例
    """
    # Try to get Anthropic settings, fall back to mock if no API key
    settings = _anthropic_settings(require_key=False)
    if settings:
        llm_service = AnthropicProvider(settings)
        logger.info("Using AnthropicProvider for Bible generation")
    else:
        from infrastructure.ai.providers.mock_provider import MockProvider
        llm_service = MockProvider()
        logger.warning("No API key found, using MockProvider for Bible generation")

    # 导入 WorldbuildingService 和 TripleRepository
    from application.services.worldbuilding_service import WorldbuildingService
    from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
    from infrastructure.persistence.database.triple_repository import TripleRepository
    from application.paths import get_db_path

    db_path = get_db_path()
    worldbuilding_repo = WorldbuildingRepository(db_path)
    worldbuilding_service = WorldbuildingService(worldbuilding_repo)
    triple_repo = TripleRepository(db_path)

    return AutoBibleGenerator(
        llm_service=llm_service,
        bible_service=get_bible_service(),
        worldbuilding_service=worldbuilding_service,
        triple_repository=triple_repo
    )


def get_state_extractor() -> StateExtractor:
    """获取状态提取器

    Returns:
        StateExtractor 实例
    """
    settings = _anthropic_settings(require_key=False)
    if settings:
        llm_service = AnthropicProvider(settings)
    else:
        from infrastructure.ai.providers.mock_provider import MockProvider
        llm_service = MockProvider()
    return StateExtractor(llm_service=llm_service)


def get_auto_knowledge_generator() -> AutoKnowledgeGenerator:
    """获取自动 Knowledge 生成器

    Returns:
        AutoKnowledgeGenerator 实例
    """
    settings = _anthropic_settings(require_key=False)
    if settings:
        llm_service = AnthropicProvider(settings)
    else:
        from infrastructure.ai.providers.mock_provider import MockProvider
        llm_service = MockProvider()
    return AutoKnowledgeGenerator(
        llm_service=llm_service,
        knowledge_service=get_knowledge_service()
    )


def get_state_updater() -> StateUpdater:
    """获取状态更新器

    Returns:
        StateUpdater 实例
    """
    return StateUpdater(
        bible_repository=get_bible_repository(),
        foreshadowing_repository=get_foreshadowing_repository(),
        knowledge_service=get_knowledge_service()
    )
