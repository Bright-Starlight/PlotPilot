from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.core.dtos.chapter_dto import ChapterDTO
from interfaces.api.dependencies import (
    get_chapter_aftermath_pipeline,
    get_chapter_service,
)
from interfaces.api.v1.core import chapters


class _FakeChapterService:
    def __init__(self, chapter: ChapterDTO):
        self.chapter = chapter
        self.update_calls: list[str] = []
        self.chapter_draft_binding_repository = type("FakeBindingRepo", (), {"upsert_binding": Mock()})()

    def get_chapter_by_novel_and_number(self, novel_id: str, chapter_number: int) -> ChapterDTO | None:
        if self.chapter.novel_id == novel_id and self.chapter.number == chapter_number:
            return self.chapter
        return None

    def update_chapter_by_novel_and_number(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        generation_metrics=None,
        draft_binding=None,
    ) -> ChapterDTO:
        assert self.chapter.novel_id == novel_id
        assert self.chapter.number == chapter_number
        self.update_calls.append(content)
        self.chapter = replace(
            self.chapter,
            content=content,
            word_count=len(content),
        )
        return self.chapter

    @staticmethod
    def _normalize_draft_binding(draft_binding: dict) -> dict:
        return draft_binding


def _build_client(service: _FakeChapterService, aftermath: dict, latest_draft=None):
    app = FastAPI()
    app.include_router(chapters.router, prefix="/api/v1/novels")
    pipeline = type("FakePipeline", (), {})()
    pipeline.run_after_chapter_saved = AsyncMock(return_value=aftermath)
    pipeline._chapter_fusion_service = SimpleNamespace(
        fusion_repository=SimpleNamespace(
            get_latest_draft_for_chapter=lambda chapter_id: latest_draft,
        )
    )

    app.dependency_overrides[get_chapter_service] = lambda: service
    app.dependency_overrides[get_chapter_aftermath_pipeline] = lambda: pipeline
    return TestClient(app), pipeline


def _chapter_dto(content: str = "旧正文") -> ChapterDTO:
    return ChapterDTO(
        id="chapter-1",
        novel_id="novel-1",
        number=1,
        title="第一章",
        content=content,
        word_count=len(content),
        status="draft",
    )


def test_update_chapter_returns_success_only_after_local_sync_succeeds():
    service = _FakeChapterService(_chapter_dto())
    client, pipeline = _build_client(
        service,
        {
            "narrative_sync_ok": True,
            "voice_sync_ok": True,
            "kg_sync_ok": True,
            "local_sync_ok": True,
            "local_sync_errors": [],
            "drift_alert": False,
            "similarity_score": 0.91,
        },
        latest_draft=SimpleNamespace(
            fusion_id="fd-1",
            plan_version=3,
            state_lock_version=5,
        ),
    )

    response = client.put(
        "/api/v1/novels/novel-1/chapters/1",
        json={"content": "新正文"},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "新正文"
    assert response.json()["aftermath"]["local_sync_ok"] is True
    assert service.chapter.content == "新正文"
    assert service.update_calls == ["新正文"]
    service.chapter_draft_binding_repository.upsert_binding.assert_called_once_with(
        chapter_id="chapter-1",
        novel_id="novel-1",
        draft_type="merged",
        draft_id="merged-current",
        plan_version=3,
        state_lock_version=5,
        source_fusion_id="fd-1",
    )
    pipeline.run_after_chapter_saved.assert_awaited_once_with("novel-1", 1, "新正文")


def test_update_chapter_rolls_back_when_local_sync_fails():
    service = _FakeChapterService(_chapter_dto())
    client, pipeline = _build_client(
        service,
        {
            "narrative_sync_ok": False,
            "voice_sync_ok": True,
            "kg_sync_ok": True,
            "local_sync_ok": False,
            "local_sync_errors": ["叙事同步失败: timeout"],
        },
    )

    response = client.put(
        "/api/v1/novels/novel-1/chapters/1",
        json={"content": "新正文"},
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["message"] == "保存失败：章后本地同步未完成，正文已回滚"
    assert detail["aftermath"]["local_sync_ok"] is False
    assert detail["aftermath"]["local_sync_errors"] == ["叙事同步失败: timeout"]
    assert service.chapter.content == "旧正文"
    assert service.update_calls == ["新正文", "旧正文"]
    service.chapter_draft_binding_repository.upsert_binding.assert_not_called()
    pipeline.run_after_chapter_saved.assert_awaited_once_with("novel-1", 1, "新正文")
