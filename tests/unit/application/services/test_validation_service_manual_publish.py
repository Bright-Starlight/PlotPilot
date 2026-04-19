"""Tests for ValidationService.manual_publish_fusion_draft."""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock

from application.core.services.validation_service import ValidationService
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId


@pytest.fixture
def mock_chapter_repository():
    return Mock()


@pytest.fixture
def mock_fusion_repository():
    return Mock()


@pytest.fixture
def mock_state_lock_service():
    return Mock()


@pytest.fixture
def mock_validation_repository():
    return Mock()


@pytest.fixture
def mock_chapter_draft_binding_repository():
    return Mock()


@pytest.fixture
def mock_story_node_repository():
    return Mock()


@pytest.fixture
def mock_knowledge_service():
    return Mock()


@pytest.fixture
def mock_bible_service():
    return Mock()


@pytest.fixture
def mock_aftermath_pipeline():
    pipeline = Mock()
    pipeline.run_after_chapter_saved = AsyncMock(return_value={
        "similarity_score": 0.95,
        "drift_alert": False,
        "narrative_sync_ok": True,
    })
    return pipeline


@pytest.fixture
def validation_service(
    mock_chapter_repository,
    mock_fusion_repository,
    mock_state_lock_service,
    mock_validation_repository,
    mock_chapter_draft_binding_repository,
    mock_story_node_repository,
    mock_knowledge_service,
    mock_bible_service,
    mock_aftermath_pipeline,
):
    return ValidationService(
        chapter_repository=mock_chapter_repository,
        fusion_repository=mock_fusion_repository,
        state_lock_service=mock_state_lock_service,
        validation_repository=mock_validation_repository,
        chapter_draft_binding_repository=mock_chapter_draft_binding_repository,
        story_node_repository=mock_story_node_repository,
        knowledge_service=mock_knowledge_service,
        bible_service=mock_bible_service,
        aftermath_pipeline=mock_aftermath_pipeline,
    )


@pytest.mark.asyncio
async def test_manual_publish_fusion_draft_success(
    validation_service,
    mock_chapter_repository,
    mock_fusion_repository,
    mock_aftermath_pipeline,
):
    """测试手动发布融合草稿成功，包含信息同步。"""
    chapter_id = "chapter-test-123"
    fusion_id = "fusion-abc"
    fusion_text = "这是融合草稿的内容。" * 100
    novel_id = "novel-test-456"
    chapter_number = 5

    # Mock 章节实体
    mock_chapter = Mock()
    mock_chapter.id = chapter_id
    mock_chapter.novel_id = NovelId(novel_id)
    mock_chapter.number = chapter_number
    mock_chapter_repository.get_by_id.return_value = mock_chapter

    # Mock 融合草稿
    mock_draft = Mock()
    mock_draft.fusion_id = fusion_id
    mock_draft.text = fusion_text
    mock_draft.plan_version = 1
    mock_draft.state_lock_version = 2
    mock_fusion_repository.get_latest_draft_for_chapter.return_value = mock_draft

    # 执行手动发布
    result = await validation_service.manual_publish_fusion_draft(chapter_id)

    # 验证结果
    assert result["chapter_id"] == chapter_id
    assert result["fusion_id"] == fusion_id
    assert result["plan_version"] == 1
    assert result["state_lock_version"] == 2
    assert result["text_length"] == len(fusion_text)
    assert result["published"] is True
    assert result["info_sync_completed"] is True
    assert result["info_sync_error"] is None

    # 验证调用
    mock_chapter_repository.get_by_id.assert_called_once_with(ChapterId(chapter_id))
    mock_fusion_repository.get_latest_draft_for_chapter.assert_called_once_with(chapter_id)
    mock_chapter.update_content.assert_called_once_with(fusion_text)
    mock_chapter_repository.save.assert_called_once_with(mock_chapter)
    validation_service.chapter_draft_binding_repository.upsert_binding.assert_called_once_with(
        chapter_id=chapter_id,
        novel_id=novel_id,
        draft_type="merged",
        draft_id="merged-current",
        plan_version=1,
        state_lock_version=2,
        source_fusion_id=fusion_id,
    )

    # 验证信息同步被调用
    mock_aftermath_pipeline.run_after_chapter_saved.assert_called_once_with(
        novel_id,
        chapter_number,
        fusion_text,
        run_quality_gate=False,
        use_fusion_draft=True,
    )


@pytest.mark.asyncio
async def test_manual_publish_fusion_draft_chapter_not_found(
    validation_service,
    mock_chapter_repository,
):
    """测试章节不存在时抛出异常。"""
    chapter_id = "chapter-nonexistent"
    mock_chapter_repository.get_by_id.return_value = None

    with pytest.raises(ValueError, match="Chapter not found"):
        await validation_service.manual_publish_fusion_draft(chapter_id)


@pytest.mark.asyncio
async def test_manual_publish_fusion_draft_no_fusion_draft(
    validation_service,
    mock_chapter_repository,
    mock_fusion_repository,
):
    """测试没有融合草稿时抛出异常。"""
    chapter_id = "chapter-test-123"

    mock_chapter = Mock()
    mock_chapter.id = chapter_id
    mock_chapter_repository.get_by_id.return_value = mock_chapter
    mock_fusion_repository.get_latest_draft_for_chapter.return_value = None

    with pytest.raises(ValueError, match="No fusion draft is available for manual publish"):
        await validation_service.manual_publish_fusion_draft(chapter_id)


@pytest.mark.asyncio
async def test_manual_publish_fusion_draft_empty_text(
    validation_service,
    mock_chapter_repository,
    mock_fusion_repository,
):
    """测试融合草稿文本为空时抛出异常。"""
    chapter_id = "chapter-test-123"

    mock_chapter = Mock()
    mock_chapter.id = chapter_id
    mock_chapter_repository.get_by_id.return_value = mock_chapter

    mock_draft = Mock()
    mock_draft.text = ""
    mock_fusion_repository.get_latest_draft_for_chapter.return_value = mock_draft

    with pytest.raises(ValueError, match="Fusion draft text is empty"):
        await validation_service.manual_publish_fusion_draft(chapter_id)


@pytest.mark.asyncio
async def test_manual_publish_fusion_draft_info_sync_failure(
    validation_service,
    mock_chapter_repository,
    mock_fusion_repository,
    mock_aftermath_pipeline,
):
    """测试信息同步失败时不影响发布结果。"""
    chapter_id = "chapter-test-123"
    fusion_id = "fusion-abc"
    fusion_text = "这是融合草稿的内容。" * 100
    novel_id = "novel-test-456"
    chapter_number = 5

    # Mock 章节实体
    mock_chapter = Mock()
    mock_chapter.id = chapter_id
    mock_chapter.novel_id = NovelId(novel_id)
    mock_chapter.number = chapter_number
    mock_chapter_repository.get_by_id.return_value = mock_chapter

    # Mock 融合草稿
    mock_draft = Mock()
    mock_draft.fusion_id = fusion_id
    mock_draft.text = fusion_text
    mock_draft.plan_version = 1
    mock_draft.state_lock_version = 2
    mock_fusion_repository.get_latest_draft_for_chapter.return_value = mock_draft

    # Mock 信息同步失败
    mock_aftermath_pipeline.run_after_chapter_saved.side_effect = Exception("Info sync failed")

    # 执行手动发布（应该成功，即使信息同步失败）
    result = await validation_service.manual_publish_fusion_draft(chapter_id)

    # 验证结果（发布成功）
    assert result["chapter_id"] == chapter_id
    assert result["fusion_id"] == fusion_id
    assert result["published"] is True
    assert result["info_sync_completed"] is False
    assert result["info_sync_error"] == "Info sync failed"

    # 验证章节内容已更新
    mock_chapter.update_content.assert_called_once_with(fusion_text)
    mock_chapter_repository.save.assert_called_once_with(mock_chapter)
