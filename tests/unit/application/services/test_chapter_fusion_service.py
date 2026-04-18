"""ChapterFusionService 单元测试。"""
from __future__ import annotations

import json
import pytest
from unittest.mock import Mock

from application.core.dtos.chapter_fusion_dto import FusionDraftDTO, FusionJobDTO, FusionSuspenseBudgetDTO
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from application.core.services.chapter_fusion_service import BeatDraft, ChapterFusionService
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.scene import Scene
from domain.novel.value_objects.novel_id import NovelId
from domain.ai.value_objects.token_usage import TokenUsage


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


class _FakeLLMService(LLMService):
    def __init__(self, payload: dict | None = None):
        self.payload = payload or {
            "text": "沈惊鸿压低呼吸，先在客栈中典当玉佩稳住局面，随后连夜赶往钱府继续追索线索。",
            "facts_used": ["典当玉佩回忆", "前往钱府"],
            "end_state": {},
            "suspense_used": 2,
            "open_questions": [],
            "model_warnings": [],
        }

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        return GenerationResult(
            content=json.dumps(self.payload, ensure_ascii=False),
            token_usage=TokenUsage(input_tokens=len(prompt.user), output_tokens=128),
        )

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
        yield json.dumps(self.payload, ensure_ascii=False)


class _FakeStateLockRepository:
    def __init__(self, present: bool = True):
        self.present = present

    def has_version(self, chapter_id: str, version: int) -> bool:
        return self.present and version > 0

    def get_version_by_chapter(self, chapter_id: str, version: int):
        if not self.has_version(chapter_id, version):
            return None
        return type("StateLockSnapshot", (), {
            "locks": {
                "ending_lock": {
                    "entries": [
                        {"key": "ending_target", "label": "目标终态", "value": "钱府", "kind": "ending_target"},
                    ]
                },
                "character_lock": {"entries": []},
                "numeric_lock": {"entries": []},
            }
        })()


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
            state_lock_repository=_FakeStateLockRepository(),
            llm_service=_FakeLLMService(),
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

    @pytest.mark.asyncio
    async def test_compose_fusion_uses_ai_output_and_deduplicates(self, service):
        result = await service._compose_fusion(
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
        assert "沈惊鸿" in result["text"]
        assert len(result["facts_confirmed"]) == 2

    @pytest.mark.asyncio
    async def test_compose_fusion_deduplicates_same_event_across_functions(self, service):
        service.llm_service = _FakeLLMService(
            {
                "text": "沈惊鸿在客栈里反复思量同一件事，最终只保留了一次有效推进。",
                "facts_used": ["同一事件"],
                "end_state": {},
                "suspense_used": 1,
                "open_questions": [],
                "model_warnings": [],
            }
        )
        result = await service._compose_fusion(
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

    @pytest.mark.asyncio
    async def test_load_beat_drafts_assigns_end_state_only_to_final_beat(self, chapter):
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
            state_lock_repository=_FakeStateLockRepository(),
            llm_service=_FakeLLMService(),
        )

        beats = await service._load_beat_drafts("ch-1", ["b1", "b2"])

        assert beats[0].end_state is None
        assert beats[1].end_state == {"location": "钱府"}

    @pytest.mark.asyncio
    async def test_compose_fusion_marks_warning_when_any_warning_exists(self, service):
        result = await service._compose_fusion(
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
            state_lock_repository=_FakeStateLockRepository(),
            llm_service=_FakeLLMService(),
        )

        with pytest.raises(ValueError, match="stored beat sheet"):
            await service._load_beat_drafts("ch-1", ["b1"])

    @pytest.mark.asyncio
    async def test_compose_fusion_fails_for_conflicting_end_states(self, service):
        result = await service._compose_fusion(
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

    @pytest.mark.asyncio
    async def test_compose_fusion_fails_when_ai_end_state_conflicts(self, chapter, scenes):
        fusion_repo = Mock()
        service = ChapterFusionService(
            chapter_repository=_FakeChapterRepository(chapter),
            beat_sheet_repository=_FakeBeatSheetRepository(scenes),
            fusion_repository=fusion_repo,
            state_lock_repository=_FakeStateLockRepository(),
            llm_service=_FakeLLMService(
                {
                    "text": "沈惊鸿在钱府落脚，却突然被写成留在客栈。",
                    "facts_used": ["前往钱府"],
                    "end_state": {"location": "客栈"},
                    "suspense_used": 1,
                    "open_questions": [],
                    "model_warnings": [],
                }
            ),
        )

        result = await service._compose_fusion(
            "第一章",
            "",
            "",
            [BeatDraft("b1", "收束", "前往钱府", "前往钱府", end_state={"location": "钱府"})],
            target_words=1200,
            suspense_budget={"primary": 1, "secondary": 0},
        )

        assert result["status"] == "failed"
        assert "conflicts" in result["message"]

    def test_create_job_blocks_when_state_lock_version_not_found(self, chapter, scenes):
        fusion_repo = Mock()
        service = ChapterFusionService(
            chapter_repository=_FakeChapterRepository(chapter),
            beat_sheet_repository=_FakeBeatSheetRepository(scenes),
            fusion_repository=fusion_repo,
            state_lock_repository=_FakeStateLockRepository(present=False),
            llm_service=_FakeLLMService(),
        )

        with pytest.raises(ValueError, match="State locks must be generated"):
            service.create_job(
                chapter_id="ch-1",
                plan_version=1,
                state_lock_version=1,
                beat_ids=["b1"],
                target_words=1800,
                suspense_budget={"primary": 1, "secondary": 1},
            )


class TestFusionJobPreview:
    def test_preview_uses_estimated_word_count_not_character_count(self):
        draft = FusionDraftDTO(
            fusion_id="fd-1",
            chapter_id="ch-1",
            plan_version=1,
            state_lock_version=1,
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
