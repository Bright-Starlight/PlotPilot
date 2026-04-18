"""Tests for ValidationService.manual_publish_fusion_draft."""
import pytest
from unittest.mock import Mock, MagicMock

from application.core.services.validation_service import ValidationService
from domain.novel.value_objects.chapter_id import ChapterId


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
def validation_service(
    mock_chapter_repository,
    mock_fusion_repository,
    mock_state_lock_service,
    mock_validation_repository,
    mock_chapter_draft_binding_repository,
    mock_story_node_repository,
    mock_knowledge_service,
    mock_bible_service,
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
    )


def test_manual_publish_fusion_draft_success(
    validation_service,
    mock_chapter_repository,
    mock_fusion_repository,
):
    """测试手动发布融合草稿成功。"""
    chapter_id = "chapter-test-123"
    fusion_id = "fusion-abc"
    fusion_text = "这是融合草稿的内容。" * 100

    # Mock 章节实体
    mock_chapter = Mock()
    mock_chapter.id = chapter_id
    mock_chapter_repository.get_by_id.return_value = mock_chapter

    # Mock 融合草稿
    mock_draft = Mock()
    mock_draft.fusion_id = fusion_id
    mock_draft.text = fusion_text
    mock_draft.plan_version = 1
    mock_draft.state_lock_version = 2
    mock_fusion_repository.get_latest_draft_for_chapter.return_value = mock_draft

    # 执行手动发布
    result = validation_service.manual_publish_fusion_draft(chapter_id)

    # 验证结果
    assert result["chapter_id"] == chapter_id
    assert result["fusion_id"] == fusion_id
    assert result["plan_version"] == 1
    assert result["state_lock_version"] == 2
    assert result["text_length"] == len(fusion_text)
    assert result["published"] is True

    # 验证调用
    mock_chapter_repository.get_by_id.assert_called_once_with(ChapterId(chapter_id))
    mock_fusion_repository.get_latest_draft_for_chapter.assert_called_once_with(chapter_id)
    mock_chapter.update_content.assert_called_once_with(fusion_text)
    mock_chapter_repository.save.assert_called_once_with(mock_chapter)


def test_manual_publish_fusion_draft_chapter_not_found(
    validation_service,
    mock_chapter_repository,
):
    """测试章节不存在时抛出异常。"""
    chapter_id = "chapter-nonexistent"
    mock_chapter_repository.get_by_id.return_value = None

    with pytest.raises(ValueError, match="Chapter not found"):
        validation_service.manual_publish_fusion_draft(chapter_id)


def test_manual_publish_fusion_draft_no_fusion_draft(
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
        validation_service.manual_publish_fusion_draft(chapter_id)


def test_manual_publish_fusion_draft_empty_text(
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
        validation_service.manual_publish_fusion_draft(chapter_id)
