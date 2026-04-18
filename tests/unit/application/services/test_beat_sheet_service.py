from __future__ import annotations

from dataclasses import dataclass

import pytest

from application.blueprint.services.beat_sheet_service import BeatSheetService


@dataclass
class _FakeNovelId:
    value: str


@dataclass
class _FakeChapter:
    novel_id: _FakeNovelId
    number: int
    title: str
    outline: str = ""
    content: str = ""


class _FakeChapterRepository:
    def __init__(self, chapter: _FakeChapter):
        self.chapter = chapter

    def get_by_id(self, chapter_id):  # noqa: ANN001
        return self.chapter


class _FakeStorylineRepository:
    def list_active_by_novel(self, novel_id):  # noqa: ANN001
        return []


class _FakeBeatSheetRepository:
    async def save(self, beat_sheet):
        return None

    async def get_by_chapter_id(self, chapter_id):  # noqa: ANN001
        return None


class _FakeLLMService:
    async def generate(self, prompt, config):  # noqa: ANN001
        raise AssertionError("LLM should not be called when state_lock_version is missing")


@pytest.mark.asyncio
async def test_generate_beat_sheet_requires_state_lock_version():
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
                outline="旧大纲",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
    )

    with pytest.raises(ValueError, match="state_lock_version is required"):
        await service.generate_beat_sheet("chapter-1", "旧大纲")
