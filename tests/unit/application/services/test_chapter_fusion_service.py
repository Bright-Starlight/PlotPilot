"""ChapterFusionService 单元测试。"""
from __future__ import annotations

import pytest
from unittest.mock import Mock

from application.core.dtos.chapter_fusion_dto import FusionDraftDTO, FusionJobDTO, FusionSuspenseBudgetDTO
from application.core.services.chapter_fusion_service import BeatDraft, ChapterFusionService
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.scene import Scene
from domain.novel.value_objects.novel_id import NovelId


class _FakeChapterRepository:
    def __init__(self, chapter: Chapter | None):
        self.chapter = chapter

    def get_by_id(self, chapter_id):  # noqa: ANN001
        return self.chapter


class _FakeBeatSheetRepository:
    def __init__(self, scenes):
        self.scenes = scenes

    async def get_by_chapter_id(self, chapter_id):  # noqa: ANN001
        return type("BeatSheet", (), {"scenes": self.scenes})()


class TestChapterFusionService:
    @pytest.fixture
    def chapter(self):
        return Chapter(
            id="ch-1",
            novel_id=NovelId("novel-1"),
            number=1,
            title="第一章",
            content="旧正文",
            outline="旧大纲",
        )

    @pytest.fixture
    def scenes(self):
        return [
            Scene(title="开场", goal="典当玉佩", pov_character="沈惊鸿", location="客栈", tone="紧张", estimated_words=500, order_index=0),
            Scene(title="转折", goal="前往钱府", pov_character="沈惊鸿", location="钱府", tone="深夜", estimated_words=600, order_index=1),
        ]

    @pytest.fixture
    def service(self, chapter, scenes):
        fusion_repo = Mock()
        fusion_repo.create_job.return_value = None
        return ChapterFusionService(
            chapter_repository=_FakeChapterRepository(chapter),
            beat_sheet_repository=_FakeBeatSheetRepository(scenes),
            fusion_repository=fusion_repo,
        )

    def test_create_job_blocks_when_state_lock_missing(self, service):
        with pytest.raises(ValueError, match="state_lock_version"):
            service.create_job(
                chapter_id="ch-1",
                plan_version=1,
                state_lock_version=0,
                beat_ids=["b1"],
                target_words=2400,
                suspense_budget={"primary": 1, "secondary": 1},
            )

    def test_compose_fusion_deduplicates_and_bridges_transitions(self, service):
        result = service._compose_fusion(
            "第一章",
            "旧正文",
            "旧大纲",
            [
                BeatDraft("b1", "开场", "典当玉佩回忆", "典当玉佩回忆", location="客栈"),
                BeatDraft("b2", "重复", "典当玉佩回忆", "典当玉佩回忆", location="客栈"),
                BeatDraft("b3", "转场", "前往钱府", "前往钱府", location="钱府"),
            ],
            target_words=300,
            suspense_budget={"primary": 1, "secondary": 1},
        )

        assert result["status"] in {"completed", "warning"}
        assert result["repeat_ratio"] > 0
        assert "随后，叙述自然过渡到钱府" in result["text"]
        assert len(result["facts_confirmed"]) == 2

    def test_compose_fusion_deduplicates_same_event_across_functions(self, service):
        result = service._compose_fusion(
            "第一章",
            "",
            "",
            [
                BeatDraft("b1", "开场", "铺垫", "同一事件", location="客栈"),
                BeatDraft("b2", "重复", "冲突", "同一事件", location="客栈"),
            ],
            target_words=300,
            suspense_budget={"primary": 1, "secondary": 1},
        )

        assert result["repeat_ratio"] == 0.5
        assert len(result["facts_confirmed"]) == 1
        assert "重复率偏高" in " ".join(result["warnings"])

    def test_compose_fusion_marks_warning_when_any_warning_exists(self, service):
        result = service._compose_fusion(
            "第一章",
            "旧正文",
            "旧大纲",
            [
                BeatDraft("b1", "开场", "典当玉佩回忆", "典当玉佩回忆", location="客栈"),
            ],
            target_words=1,
            suspense_budget={"primary": 0, "secondary": 0},
        )

        assert result["status"] == "warning"
        assert "裁剪" in " ".join(result["warnings"])
        assert "悬念预算" in " ".join(result["open_questions"])

    @pytest.mark.asyncio
    async def test_load_beat_drafts_rejects_length_mismatch(self, chapter):
        fusion_repo = Mock()
        service = ChapterFusionService(
            chapter_repository=_FakeChapterRepository(chapter),
            beat_sheet_repository=_FakeBeatSheetRepository(
                [
                    Scene(title="开场", goal="典当玉佩", pov_character="沈惊鸿", location="客栈", tone="紧张", estimated_words=500, order_index=0),
                    Scene(title="转折", goal="前往钱府", pov_character="沈惊鸿", location="钱府", tone="深夜", estimated_words=600, order_index=1),
                ]
            ),
            fusion_repository=fusion_repo,
        )

        with pytest.raises(ValueError, match="stored beat sheet"):
            await service._load_beat_drafts("ch-1", ["b1"])

    def test_compose_fusion_fails_for_conflicting_end_states(self, service):
        result = service._compose_fusion(
            "第一章",
            "",
            "",
            [
                BeatDraft("b1", "开场", "开场", "开场", end_state={"location": "刚入府"}),
                BeatDraft("b2", "收束", "收束", "收束", end_state={"location": "夜探后院"}),
            ],
            target_words=1200,
            suspense_budget={"primary": 1, "secondary": 1},
        )

        assert result["status"] == "failed"
        assert "not unique" in result["message"]


class TestFusionJobPreview:
    def test_preview_uses_estimated_word_count_not_character_count(self):
        draft = FusionDraftDTO(
            fusion_id="fd-1",
            chapter_id="ch-1",
            text="第一章 开场叙述与推进, second beat arrives.",
            estimated_repeat_ratio=0.1,
            warnings=[],
        )
        job = FusionJobDTO(
            fusion_job_id="fj-1",
            chapter_id="ch-1",
            plan_version=1,
            state_lock_version=1,
            beat_ids=["b1"],
            target_words=800,
            suspense_budget=FusionSuspenseBudgetDTO(primary=1, secondary=1),
            status="completed",
            fusion_draft=draft,
        )

        assert job.preview["estimated_words"] != len(draft.text)
        assert job.preview["estimated_words"] > 0
