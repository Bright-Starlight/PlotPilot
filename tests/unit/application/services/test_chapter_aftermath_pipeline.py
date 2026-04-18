"""ChapterAftermathPipeline 质量门禁测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId


class _FakeChapterRepository:
    def __init__(self, chapter: Chapter):
        self.chapter = chapter

    def get_by_novel_and_number(self, novel_id, number):  # noqa: ANN001
        if str(novel_id) == str(self.chapter.novel_id) and int(number) == int(self.chapter.number):
            return self.chapter
        return None

    def list_by_novel(self, novel_id):  # noqa: ANN001
        if str(novel_id) == str(self.chapter.novel_id):
            return [self.chapter]
        return []


def _build_pipeline(blocking_issue_count: int = 0):
    chapter = Chapter(
        id="chapter-1",
        novel_id=NovelId("novel-1"),
        number=1,
        title="第一章",
        content="旧正文",
        outline="旧大纲",
    )

    state_lock_service = Mock()
    state_lock_service.generate_state_locks = AsyncMock(
        return_value=SimpleNamespace(version=2, plan_version=3)
    )

    fusion_service = Mock()
    fusion_service.beat_sheet_repository = Mock()
    fusion_service.beat_sheet_repository.get_by_chapter_id = AsyncMock(
        return_value=SimpleNamespace(
            scenes=[
                SimpleNamespace(
                    title="开场",
                    goal="建立局势",
                    pov_character="沈惊鸿",
                    location="客栈",
                    tone="紧张",
                    estimated_words=500,
                    order_index=0,
                ),
                SimpleNamespace(
                    title="转折",
                    goal="前往钱府",
                    pov_character="沈惊鸿",
                    location="钱府",
                    tone="深夜",
                    estimated_words=600,
                    order_index=1,
                ),
            ],
            state_lock_version=1,
            plan_version=3,
        )
    )
    fusion_service.create_job.return_value = SimpleNamespace(fusion_job_id="fj-1")
    fusion_service.run_job = AsyncMock(
        return_value=SimpleNamespace(
            fusion_job_id="fj-1",
            status="completed",
            fusion_draft=SimpleNamespace(
                fusion_id="fd-1",
                latest_validation_report_id="vr-1",
            ),
        )
    )
    fusion_service.validation_service = Mock()
    fusion_service.validation_service.get_report.return_value = SimpleNamespace(
        report_id="vr-1",
        blocking_issue_count=blocking_issue_count,
        status="completed" if blocking_issue_count == 0 else "failed",
    )

    refreshed_beat_sheet = SimpleNamespace(
        scenes=[
            SimpleNamespace(
                title="开场",
                goal="建立局势",
                pov_character="沈惊鸿",
                location="客栈",
                tone="紧张",
                estimated_words=500,
                order_index=0,
            ),
            SimpleNamespace(
                title="转折",
                goal="前往钱府",
                pov_character="沈惊鸿",
                location="钱府",
                tone="深夜",
                estimated_words=600,
                order_index=1,
            ),
        ],
        state_lock_version=2,
        plan_version=3,
    )
    stale_beat_sheet = SimpleNamespace(
        scenes=refreshed_beat_sheet.scenes,
        state_lock_version=1,
        plan_version=3,
    )
    fusion_service.beat_sheet_repository.get_by_chapter_id.return_value = stale_beat_sheet

    beat_sheet_service = Mock()
    async def _generate_beat_sheet(**kwargs):
        fusion_service.beat_sheet_repository.get_by_chapter_id.return_value = refreshed_beat_sheet
        payload = {"id": "bs-1", "scenes": refreshed_beat_sheet.scenes}
        payload.update(kwargs)
        return SimpleNamespace(**payload)

    beat_sheet_service.generate_beat_sheet = AsyncMock(side_effect=_generate_beat_sheet)

    return ChapterAftermathPipeline(
        knowledge_service=Mock(),
        chapter_indexing_service=Mock(),
        llm_service=Mock(),
        voice_drift_service=None,
        chapter_repository=_FakeChapterRepository(chapter),
        state_lock_service=state_lock_service,
        chapter_fusion_service=fusion_service,
        beat_sheet_service=beat_sheet_service,
    ), state_lock_service, fusion_service, beat_sheet_service


@pytest.mark.asyncio
async def test_run_after_chapter_saved_executes_quality_gate_before_sync():
    pipeline, state_lock_service, fusion_service, beat_sheet_service = _build_pipeline(blocking_issue_count=0)

    with patch(
        "application.world.services.chapter_narrative_sync.sync_chapter_narrative_after_save",
        new_callable=AsyncMock,
    ) as sync_mock, patch(
        "application.engine.services.chapter_aftermath_pipeline.infer_kg_from_chapter",
        new_callable=AsyncMock,
    ) as kg_mock:
        result = await pipeline.run_after_chapter_saved("novel-1", 1, "章节正文", run_quality_gate=True)

    assert result["quality_gate_passed"] is True
    assert result["fusion_id"] == "fd-1"
    assert result["validation_report_id"] == "vr-1"
    state_lock_service.generate_state_locks.assert_awaited_once()
    beat_sheet_service.generate_beat_sheet.assert_awaited_once_with(
        chapter_id="chapter-1",
        outline="旧大纲",
        plan_version=3,
        state_lock_version=2,
    )
    fusion_service.create_job.assert_called_once()
    fusion_service.run_job.assert_awaited_once()
    sync_mock.assert_awaited_once()
    kg_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_after_chapter_saved_blocks_sync_when_validation_has_blocking_issues():
    pipeline, state_lock_service, fusion_service, beat_sheet_service = _build_pipeline(blocking_issue_count=1)

    with patch(
        "application.world.services.chapter_narrative_sync.sync_chapter_narrative_after_save",
        new_callable=AsyncMock,
    ) as sync_mock, patch(
        "application.engine.services.chapter_aftermath_pipeline.infer_kg_from_chapter",
        new_callable=AsyncMock,
    ) as kg_mock:
        result = await pipeline.run_after_chapter_saved("novel-1", 1, "章节正文", run_quality_gate=True)

    assert result["quality_gate_passed"] is False
    assert result["quality_gate_step"] == "validation"
    assert result["validation_report_id"] == "vr-1"
    state_lock_service.generate_state_locks.assert_awaited_once()
    beat_sheet_service.generate_beat_sheet.assert_awaited_once()
    fusion_service.create_job.assert_called_once()
    fusion_service.run_job.assert_awaited_once()
    sync_mock.assert_not_awaited()
    kg_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_after_chapter_saved_skips_quality_gate_by_default():
    pipeline, state_lock_service, fusion_service, beat_sheet_service = _build_pipeline(blocking_issue_count=0)

    with patch(
        "application.world.services.chapter_narrative_sync.sync_chapter_narrative_after_save",
        new_callable=AsyncMock,
    ) as sync_mock, patch(
        "application.engine.services.chapter_aftermath_pipeline.infer_kg_from_chapter",
        new_callable=AsyncMock,
    ) as kg_mock:
        result = await pipeline.run_after_chapter_saved("novel-1", 1, "章节正文")

    assert result["quality_gate_passed"] is True
    assert result.get("fusion_id", "") == ""
    assert result.get("validation_report_id", "") == ""
    state_lock_service.generate_state_locks.assert_not_awaited()
    beat_sheet_service.generate_beat_sheet.assert_not_awaited()
    fusion_service.create_job.assert_not_called()
    fusion_service.run_job.assert_not_awaited()
    sync_mock.assert_awaited_once()
    kg_mock.assert_awaited_once()
