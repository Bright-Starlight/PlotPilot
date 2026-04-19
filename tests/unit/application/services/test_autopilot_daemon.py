"""AutopilotDaemon 辅助逻辑测试"""
from datetime import datetime, timezone
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from application.engine.dtos.word_control_dto import WordControlDTO
from application.engine.services.autopilot_daemon import AutopilotDaemon
from domain.ai.value_objects.prompt import Prompt
from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId


def _build_novel(target_words_per_chapter: int = 3200) -> Novel:
    return Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="作者",
        target_chapters=10,
        target_words_per_chapter=target_words_per_chapter,
        autopilot_status=AutopilotStatus.RUNNING,
        current_stage=NovelStage.WRITING,
    )


def _build_workflow(action: str) -> Mock:
    workflow = Mock()
    workflow.prepare_chapter_generation.return_value = {
        "context": "ctx",
        "context_tokens": 12,
        "storyline_context": "",
        "plot_tension": 5,
        "style_summary": "",
        "voice_anchors": "",
    }
    workflow.build_chapter_prompt.return_value = Prompt(system="system", user="user")
    workflow.post_process_generated_chapter = AsyncMock()
    workflow._apply_word_control = AsyncMock(
        return_value=(
            f"修正后正文-{action}",
            SimpleNamespace(action=action),
        )
    )
    workflow._serialize_word_control.return_value = WordControlDTO(
        target=3200,
        actual=3180 if action == "expand" else 3090,
        tolerance=0.15,
        delta=-20 if action == "expand" else -110,
        status="ok",
        within_tolerance=True,
        action=action,
        expansion_attempts=1 if action == "expand" else 0,
        trim_applied=action == "trim",
        fallback_used=False,
        min_allowed=2720,
        max_allowed=3680,
    )
    workflow.word_control_service = Mock()
    workflow.word_control_service.inject_length_requirements.side_effect = _inject_length_requirements
    return workflow


def _inject_length_requirements(prompt, target):
    if isinstance(prompt, Prompt):
        return Prompt(system=prompt.system, user=f"{prompt.user}|target={target}")
    return prompt


def _build_needs_expansion_workflow() -> Mock:
    workflow = _build_workflow("expand")
    workflow._apply_word_control = AsyncMock(
        return_value=(
            "欠字正文",
            SimpleNamespace(action="needs_expansion"),
        )
    )
    workflow._serialize_word_control.return_value = WordControlDTO(
        target=3200,
        actual=1200,
        tolerance=0.15,
        delta=-2000,
        status="needs_expansion",
        within_tolerance=False,
        action="needs_expansion",
        expansion_attempts=2,
        trim_applied=False,
        fallback_used=True,
        min_allowed=2720,
        max_allowed=3680,
    )
    return workflow


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["expand", "trim"])
async def test_handle_writing_persists_word_control_metrics(action: str):
    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = None
    metrics_repository = Mock()
    workflow = _build_workflow(action)

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        chapter_workflow=workflow,
        chapter_generation_metrics_repository=metrics_repository,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._flush_novel = Mock()
    daemon._find_next_unwritten_chapter_async = AsyncMock(
        return_value=SimpleNamespace(
            id="chapter-node-1",
            number=1,
            title="第一章",
            outline="章节大纲",
            description="",
        )
    )
    daemon._get_existing_chapter_content = AsyncMock(return_value="")
    daemon._stream_llm_with_stop_watch = AsyncMock(return_value="原始正文")
    daemon._maybe_rewrite_next_chapter_outline = AsyncMock(return_value=None)

    novel = _build_novel()

    await daemon._handle_writing(novel)

    workflow._apply_word_control.assert_awaited_once()
    workflow._serialize_word_control.assert_called_once()
    metrics_repository.upsert.assert_called_once()

    upsert_args = metrics_repository.upsert.call_args.args
    assert upsert_args[0] == "novel-1"
    assert upsert_args[1] == 1
    assert upsert_args[2]["generated_via"] == "autopilot"
    assert upsert_args[2]["action"] == action
    assert upsert_args[2]["within_tolerance"] is True
    assert novel.current_stage == NovelStage.AUDITING
    assert novel.current_auto_chapters == 1


@pytest.mark.asyncio
async def test_handle_writing_stops_autopilot_when_outline_rewrite_exhausted():
    """下一章大纲重写连续失败时，应退出托管而不是继续进入下一章。"""
    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = None
    novel_repository = Mock()
    workflow = _build_workflow("expand")

    daemon = AutopilotDaemon(
        novel_repository=novel_repository,
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        chapter_workflow=workflow,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._flush_novel = Mock()
    daemon._find_next_unwritten_chapter_async = AsyncMock(
        return_value=SimpleNamespace(
            id="chapter-node-1",
            number=1,
            title="第一章",
            outline="章节大纲",
            description="",
        )
    )
    daemon._get_existing_chapter_content = AsyncMock(return_value="")
    daemon._stream_llm_with_stop_watch = AsyncMock(return_value="原始正文")
    daemon._maybe_rewrite_next_chapter_outline = AsyncMock(
        side_effect=RuntimeError("自动重写大纲连续失败: API returned no text content")
    )

    novel = _build_novel()

    await daemon._handle_writing(novel)

    assert novel.autopilot_status == AutopilotStatus.STOPPED
    novel_repository.save.assert_called_once_with(novel)
    daemon._maybe_rewrite_next_chapter_outline.assert_awaited_once()
    assert novel.current_stage == NovelStage.WRITING
    assert novel.current_auto_chapters == 0


@pytest.mark.asyncio
async def test_handle_writing_stops_for_manual_expansion_when_word_control_fails():
    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = None
    novel_repository = Mock()
    metrics_repository = Mock()
    workflow = _build_needs_expansion_workflow()

    daemon = AutopilotDaemon(
        novel_repository=novel_repository,
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        chapter_workflow=workflow,
        chapter_generation_metrics_repository=metrics_repository,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._flush_novel = Mock()
    daemon._find_next_unwritten_chapter_async = AsyncMock(
        return_value=SimpleNamespace(
            id="chapter-node-1",
            number=1,
            title="第一章",
            outline="章节大纲",
            description="",
        )
    )
    daemon._get_existing_chapter_content = AsyncMock(return_value="")
    daemon._stream_llm_with_stop_watch = AsyncMock(return_value="原始正文")

    novel = _build_novel()

    await daemon._handle_writing(novel)

    assert novel.autopilot_status == AutopilotStatus.STOPPED
    assert novel.current_stage == NovelStage.WRITING
    assert novel.last_audit_issues[0]["type"] == "needs_expansion"
    metrics_repository.upsert.assert_called_once()
    daemon._flush_novel.assert_called()


@pytest.mark.asyncio
async def test_handle_writing_uses_per_beat_target_for_length_requirements():
    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = None
    metrics_repository = Mock()
    workflow = _build_workflow("expand")
    context_builder = Mock()
    context_builder.magnify_outline_to_beats.return_value = [
        SimpleNamespace(focus="开场", description="第一拍", target_words=180),
    ]
    context_builder.build_beat_prompt.return_value = "beat prompt"

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=context_builder,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        chapter_workflow=workflow,
        chapter_generation_metrics_repository=metrics_repository,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._flush_novel = Mock()
    daemon._find_next_unwritten_chapter_async = AsyncMock(
        return_value=SimpleNamespace(
            id="chapter-node-1",
            number=1,
            title="第一章",
            outline="章节大纲",
            description="",
        )
    )
    daemon._get_existing_chapter_content = AsyncMock(return_value="")
    daemon._stream_llm_with_stop_watch = AsyncMock(
        return_value=(
            "他抬手推门，冷声道：“进来。”寒意顺着门缝卷进来。"
            "他向前一步，逼得对方后退，桌角都被撞得轻响，空气一下绷紧。"
            "屋里几个人同时收声，视线都落在那封染了雨痕的密信上。"
        )
    )
    daemon._maybe_rewrite_next_chapter_outline = AsyncMock(return_value=None)

    novel = _build_novel()

    await daemon._handle_writing(novel)

    targets = [call.kwargs["target"] for call in workflow.word_control_service.inject_length_requirements.call_args_list]
    assert 180 in targets


@pytest.mark.asyncio
async def test_handle_auditing_retries_quality_gate_before_stopping():
    chapter_repository = Mock()
    chapter_repository.list_by_novel.return_value = [
        Mock(number=1, status=Mock(value="completed"), id="chapter-1", content="旧正文"),
    ]
    aftermath_pipeline = Mock()
    # 首次质量门禁失败
    aftermath_pipeline._run_quality_gate = AsyncMock(side_effect=[
        {
            "quality_gate_passed": False,
            "quality_gate_mode": "full",
            "quality_gate_step": "validation",
            "quality_gate_reason": "Validation 有阻断问题",
            "quality_gate_blockers": ["Validation 有阻断问题"],
        },
        # 重试成功
        {
            "quality_gate_passed": True,
            "quality_gate_mode": "retry",
            "quality_gate_step": "pass",
            "quality_gate_reason": "",
            "quality_gate_blockers": [],
            "state_lock_version": 2,
            "fusion_id": "fd-1",
            "validation_report_id": "vr-1",
            "validation_status": "completed",
        }
    ])
    # 门禁通过后执行信息同步
    aftermath_pipeline.run_after_chapter_saved = AsyncMock(
        return_value={
            "drift_alert": False,
            "similarity_score": 0.92,
            "narrative_sync_ok": True,
            "quality_gate_passed": True,
        }
    )

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        aftermath_pipeline=aftermath_pipeline,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._score_voice_only = AsyncMock(return_value={"drift_alert": False, "similarity_score": 0.9})
    daemon._apply_voice_rewrite_loop = AsyncMock(return_value=("旧正文", {"drift_alert": False, "similarity_score": 0.9}))
    daemon._auto_trigger_macro_diagnosis = AsyncMock()
    daemon._maybe_generate_summaries = AsyncMock()

    novel = _build_novel()
    novel.current_stage = NovelStage.AUDITING

    await daemon._handle_auditing(novel)

    # 验证：质量门禁调用 2 次（首次 + 重试），信息同步调用 1 次
    assert aftermath_pipeline._run_quality_gate.await_count == 2
    aftermath_pipeline.run_after_chapter_saved.assert_awaited_once()
    daemon._auto_trigger_macro_diagnosis.assert_awaited_once()
    daemon._maybe_generate_summaries.assert_awaited_once()
    assert novel.autopilot_status == AutopilotStatus.RUNNING
    assert novel.current_stage == NovelStage.WRITING
    assert novel.last_audit_narrative_ok is True


@pytest.mark.asyncio
async def test_handle_auditing_stops_when_quality_gate_retry_fails():
    chapter_repository = Mock()
    chapter_repository.list_by_novel.return_value = [
        Mock(number=1, status=Mock(value="completed"), id="chapter-1", content="旧正文"),
    ]
    aftermath_pipeline = Mock()
    # 首次质量门禁失败，重试也失败
    aftermath_pipeline._run_quality_gate = AsyncMock(side_effect=[
        {
            "quality_gate_passed": False,
            "quality_gate_mode": "full",
            "quality_gate_step": "validation",
            "quality_gate_reason": "Validation 有阻断问题",
            "quality_gate_blockers": ["Validation 有阻断问题"],
        },
        {
            "quality_gate_passed": False,
            "quality_gate_mode": "retry",
            "quality_gate_step": "validation",
            "quality_gate_reason": "Validation 仍有 1 个阻断问题",
            "quality_gate_blockers": ["Validation 仍有 1 个阻断问题"],
            "state_lock_version": 2,
            "fusion_id": "fd-1",
            "validation_report_id": "vr-1",
            "validation_status": "failed",
        }
    ])
    # 不应该调用信息同步
    aftermath_pipeline.run_after_chapter_saved = AsyncMock()

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        aftermath_pipeline=aftermath_pipeline,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._score_voice_only = AsyncMock(return_value={"drift_alert": False, "similarity_score": 0.9})
    daemon._apply_voice_rewrite_loop = AsyncMock(return_value=("旧正文", {"drift_alert": False, "similarity_score": 0.9}))
    daemon._auto_trigger_macro_diagnosis = AsyncMock()
    daemon._maybe_generate_summaries = AsyncMock()

    novel = _build_novel()
    novel.current_stage = NovelStage.AUDITING

    await daemon._handle_auditing(novel)

    # 验证：质量门禁调用 2 次（首次 + 重试），信息同步不应该被调用
    assert aftermath_pipeline._run_quality_gate.await_count == 2
    aftermath_pipeline.run_after_chapter_saved.assert_not_awaited()
    daemon._auto_trigger_macro_diagnosis.assert_not_awaited()
    daemon._maybe_generate_summaries.assert_not_awaited()
    assert novel.autopilot_status == AutopilotStatus.STOPPED
    assert novel.current_stage == NovelStage.AUDITING
    assert novel.last_audit_narrative_ok is False


@pytest.mark.asyncio
async def test_handle_auditing_skips_when_latest_fusion_is_already_published():
    chapter = Mock(number=1, status=Mock(value="completed"), id="chapter-1", content="已发布正文")
    chapter_repository = Mock()
    chapter_repository.list_by_novel.return_value = [chapter]

    fusion_repository = Mock()
    fusion_repository.get_latest_draft_for_chapter.return_value = SimpleNamespace(
        fusion_id="fd-1",
        plan_version=3,
        state_lock_version=5,
    )
    fusion_service = Mock(fusion_repository=fusion_repository)
    aftermath_pipeline = Mock()
    aftermath_pipeline._chapter_fusion_service = fusion_service
    aftermath_pipeline._run_quality_gate = AsyncMock()
    aftermath_pipeline.run_after_chapter_saved = AsyncMock()

    binding_repository = Mock()
    binding_repository.get_binding.return_value = SimpleNamespace(
        source_fusion_id="fd-1",
        plan_version=3,
        state_lock_version=5,
    )

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        aftermath_pipeline=aftermath_pipeline,
        chapter_draft_binding_repository=binding_repository,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._score_voice_only = AsyncMock()
    daemon._apply_voice_rewrite_loop = AsyncMock()
    daemon._auto_trigger_macro_diagnosis = AsyncMock()
    daemon._maybe_generate_summaries = AsyncMock()

    novel = _build_novel()
    novel.current_stage = NovelStage.AUDITING

    await daemon._handle_auditing(novel)

    binding_repository.get_binding.assert_called_once_with(
        chapter_id="chapter-1",
        draft_type="merged",
        draft_id="merged-current",
    )
    aftermath_pipeline._run_quality_gate.assert_not_awaited()
    aftermath_pipeline.run_after_chapter_saved.assert_not_awaited()
    daemon._auto_trigger_macro_diagnosis.assert_not_awaited()
    daemon._maybe_generate_summaries.assert_not_awaited()
    assert novel.current_stage == NovelStage.WRITING
    assert novel.last_audit_chapter_number == 1
    assert novel.last_audit_narrative_ok is True


@pytest.mark.asyncio
async def test_process_novel_skips_duplicate_auditing_for_same_chapter():
    chapter_repository = Mock()
    chapter_repository.list_by_novel.return_value = [
        Mock(
            number=1,
            status=Mock(value="completed"),
            id="chapter-1",
            content="旧正文",
            updated_at=datetime(2026, 4, 18, 21, 8, 0),
        ),
    ]

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        aftermath_pipeline=Mock(),
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._handle_auditing = AsyncMock()
    daemon._handle_macro_planning = AsyncMock()
    daemon._handle_act_planning = AsyncMock()
    daemon._handle_writing = AsyncMock()

    novel = _build_novel()
    novel.current_stage = NovelStage.AUDITING
    novel.last_audit_chapter_number = 1
    novel.last_audit_at = "2026-04-18T21:08:30+00:00"

    await daemon._process_novel(novel)

    daemon._handle_auditing.assert_not_awaited()
    chapter_repository.list_by_novel.assert_called_once()


@pytest.mark.asyncio
async def test_maybe_rewrite_next_chapter_outline_syncs_title_and_description():
    """重写下一章大纲时，应同步更新标题与描述。"""
    story_node_repo = Mock()
    story_node_repo.update = AsyncMock()
    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=story_node_repo,
        chapter_repository=Mock(),
    )

    next_node = SimpleNamespace(
        id="chapter-node-2",
        number=2,
        title="旧标题",
        outline="旧大纲",
        description="旧描述",
        metadata={},
    )
    seam = {
        "ending_state": "主角冲进密室",
        "ending_emotion": "紧张",
        "carry_over_question": "密室里到底有什么",
        "next_opening_hint": "密室内部会有机关",
    }

    daemon._find_chapter_node_after = AsyncMock(return_value=next_node)
    daemon._build_chapter_seam_snapshot = Mock(return_value=seam)
    daemon._outline_conflicts_with_previous_seam = Mock(return_value=(True, "测试冲突"))
    daemon._rewrite_next_chapter_outline = AsyncMock(
        return_value={
            "outline": "主角进入密室后发现墙壁机关，必须先破解机关才能继续前进。",
            "title": "密室机关",
            "description": "主角在密室中破解机关。",
        }
    )

    novel = _build_novel()
    current_chapter = SimpleNamespace(number=1)

    await daemon._maybe_rewrite_next_chapter_outline(
        novel=novel,
        current_chapter_node=current_chapter,
        current_outline="当前章大纲",
        current_content="当前章内容",
    )

    assert next_node.outline == "主角进入密室后发现墙壁机关，必须先破解机关才能继续前进。"
    assert next_node.title == "密室机关"
    assert next_node.description == "主角在密室中破解机关。"
    assert next_node.metadata["auto_replanned_title"] == "密室机关"
    assert next_node.metadata["auto_replanned_outline"] == next_node.outline
    assert next_node.metadata["auto_replanned_description"] == next_node.description
    story_node_repo.update.assert_awaited_once_with(next_node)


def test_get_latest_completed_chapter_prefers_highest_number():
    """审计阶段应按真实章节号选择最近完成章节。"""
    chapters = [
        Mock(number=11, status=Mock(value="completed")),
        Mock(number=12, status=Mock(value="draft")),
        Mock(number=13, status=Mock(value="completed")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter.number == 13


def test_get_latest_completed_chapter_returns_none_when_no_completed():
    """没有完成章节时应返回 None。"""
    chapters = [
        Mock(number=11, status=Mock(value="draft")),
        Mock(number=12, status=Mock(value="reviewing")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter is None
