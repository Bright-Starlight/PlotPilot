"""Tests for LLM validators."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from application.core.services.validators import (
    ChapterCoherenceValidator,
    CharacterReactionValidator,
    SuspenseResolutionValidator,
    ValidationResult,
    ValidationIssue,
)


@pytest.fixture
def mock_llm_service():
    """Mock LLM service."""
    service = MagicMock()
    service.generate = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_coherence_validator_success(mock_llm_service):
    """测试连贯性验证器 - 成功场景"""
    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = '{"is_coherent": true, "issues": [], "suggestions": []}'
    mock_llm_service.generate.return_value = mock_response

    validator = ChapterCoherenceValidator(mock_llm_service)
    result = await validator.validate(
        previous_chapter_content="上一章内容...",
        current_chapter_content="当前章内容...",
        previous_chapter_seam={
            "ending_state": "沈墨白站在废墟中",
            "unfinished_speech": "",
            "carry_over_question": "",
            "ending_emotion": "沉重",
        },
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert len(result.issues) == 0


@pytest.mark.asyncio
async def test_coherence_validator_with_issues(mock_llm_service):
    """测试连贯性验证器 - 发现问题"""
    # Mock LLM response with issues
    mock_response = MagicMock()
    mock_response.content = '''{
        "is_coherent": false,
        "issues": [
            {
                "type": "missing_transition",
                "severity": "high",
                "description": "章节开头缺少承接上一章的过渡"
            }
        ],
        "suggestions": ["在开头添加过渡句"]
    }'''
    mock_llm_service.generate.return_value = mock_response

    validator = ChapterCoherenceValidator(mock_llm_service)
    result = await validator.validate(
        previous_chapter_content="上一章内容...",
        current_chapter_content="当前章内容...",
        previous_chapter_seam={
            "ending_state": "沈墨白站在废墟中",
            "unfinished_speech": "而我——",
            "carry_over_question": "她是谁？",
            "ending_emotion": "沉重",
        },
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is False
    assert len(result.issues) == 1
    assert result.issues[0].type == "missing_transition"
    assert result.issues[0].severity == "high"
    assert len(result.suggestions) == 1


@pytest.mark.asyncio
async def test_character_reaction_validator_success(mock_llm_service):
    """测试人物反应验证器 - 成功场景"""
    mock_response = MagicMock()
    mock_response.content = '{"all_reacted": true, "missing_reactions": [], "suggestions": []}'
    mock_llm_service.generate.return_value = mock_response

    validator = CharacterReactionValidator(mock_llm_service)
    result = await validator.validate(
        chapter_content="章节内容...",
        key_characters=["沈墨白", "顾玄音", "郑奉安"],
        key_events=["女鬼朱璃现身", "朱璃控诉沈墨白"],
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert len(result.issues) == 0


@pytest.mark.asyncio
async def test_character_reaction_validator_with_missing_reactions(mock_llm_service):
    """测试人物反应验证器 - 发现缺失反应"""
    mock_response = MagicMock()
    mock_response.content = '''{
        "all_reacted": false,
        "missing_reactions": [
            {
                "character": "郑奉安",
                "event": "女鬼朱璃现身",
                "severity": "high",
                "reason": "郑奉安在场但没有任何反应"
            }
        ],
        "suggestions": ["在XX处增加郑奉安的反应"]
    }'''
    mock_llm_service.generate.return_value = mock_response

    validator = CharacterReactionValidator(mock_llm_service)
    result = await validator.validate(
        chapter_content="章节内容...",
        key_characters=["沈墨白", "顾玄音", "郑奉安"],
        key_events=["女鬼朱璃现身"],
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is False
    assert len(result.issues) == 1
    assert "郑奉安" in result.issues[0].description


@pytest.mark.asyncio
async def test_suspense_validator_no_suspense(mock_llm_service):
    """测试悬念解答验证器 - 无悬念场景"""
    validator = SuspenseResolutionValidator(mock_llm_service)
    result = await validator.validate(
        previous_suspense=[],
        current_chapter_content="章节内容...",
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert len(result.issues) == 0
    assert result.metadata.get("note") == "无悬念需要验证"


@pytest.mark.asyncio
async def test_suspense_validator_with_unhandled_suspense(mock_llm_service):
    """测试悬念解答验证器 - 发现未处理悬念"""
    mock_response = MagicMock()
    mock_response.content = '''{
        "all_handled": false,
        "unhandled_suspense": [
            {
                "suspense": "她是谁？",
                "status": "ignored",
                "severity": "critical",
                "reason": "这个问题在本章完全没有提及"
            }
        ],
        "suggestions": ["在XX处回应'她是谁'这个问题"]
    }'''
    mock_llm_service.generate.return_value = mock_response

    validator = SuspenseResolutionValidator(mock_llm_service)
    result = await validator.validate(
        previous_suspense=["她是谁？", "不该救的人是谁？"],
        current_chapter_content="章节内容...",
    )

    assert isinstance(result, ValidationResult)
    assert result.is_valid is False
    assert len(result.issues) == 1
    assert "她是谁" in result.issues[0].description


@pytest.mark.asyncio
async def test_validator_handles_llm_error(mock_llm_service):
    """测试验证器处理 LLM 错误"""
    # Mock LLM to raise an exception
    mock_llm_service.generate.side_effect = Exception("LLM service error")

    validator = ChapterCoherenceValidator(mock_llm_service)
    result = await validator.validate(
        previous_chapter_content="上一章内容...",
        current_chapter_content="当前章内容...",
        previous_chapter_seam={},
    )

    # 验证失败时应该默认通过
    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert len(result.issues) == 0
    assert "error" in result.metadata
