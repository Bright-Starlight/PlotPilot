"""章节融合服务。"""
from __future__ import annotations

import asyncio
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.chapter_id import ChapterId
from infrastructure.persistence.database.sqlite_beat_sheet_repository import SqliteBeatSheetRepository
from infrastructure.persistence.database.sqlite_chapter_fusion_repository import SqliteChapterFusionRepository


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


@dataclass
class BeatDraft:
    beat_id: str
    title: str
    function: str
    event: str
    location: str = ""
    end_state: Optional[Dict[str, Any]] = None


class ChapterFusionService:
    def __init__(
        self,
        chapter_repository: ChapterRepository,
        beat_sheet_repository: SqliteBeatSheetRepository,
        fusion_repository: SqliteChapterFusionRepository,
    ):
        self.chapter_repository = chapter_repository
        self.beat_sheet_repository = beat_sheet_repository
        self.fusion_repository = fusion_repository

    def create_job(
        self,
        chapter_id: str,
        plan_version: int,
        state_lock_version: int,
        beat_ids: List[str],
        target_words: int,
        suspense_budget: Dict[str, Any],
    ):
        chapter = self._get_chapter(chapter_id)
        if chapter is None:
            raise ValueError("Chapter not found")
        if plan_version <= 0:
            raise ValueError("plan_version is required")
        if state_lock_version <= 0:
            raise ValueError("state_lock_version is required")
        if not beat_ids:
            raise ValueError("BeatDrafts are required")

        job_id = f"fj_{uuid.uuid4().hex[:8]}"
        job = self.fusion_repository.create_job(
            job_id,
            chapter_id,
            chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id),
            plan_version,
            state_lock_version,
            beat_ids,
            target_words,
            suspense_budget,
        )
        self.fusion_repository.add_log(job_id, chapter_id, "create", "queued", "fusion job queued")
        return job

    async def run_job(self, fusion_job_id: str):
        job = self.fusion_repository.get_job(fusion_job_id)
        if job is None:
            raise ValueError("Fusion job not found")
        self.fusion_repository.update_job_status(fusion_job_id, "running")
        self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "validate", "running", "validating inputs")

        chapter = self._get_chapter(job.chapter_id)
        if chapter is None:
            return self._fail_job(job.fusion_job_id, job.chapter_id, "chapter_missing", "Chapter not found")

        try:
            beat_drafts = await self._load_beat_drafts(job.chapter_id, job.beat_ids)
        except ValueError as exc:
            self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "validate", "failed", str(exc))
            return self._fail_job(job.fusion_job_id, job.chapter_id, "beats_invalid", str(exc))
        if not beat_drafts:
            return self._fail_job(job.fusion_job_id, job.chapter_id, "beats_missing", "BeatDrafts are missing")

        result = self._compose_fusion(chapter.title, chapter.content or "", chapter.outline or "", beat_drafts, job.target_words, job.suspense_budget.__dict__)
        if result["status"] == "failed":
            self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "compose", "failed", result["message"])
            self.fusion_repository.update_job_status(fusion_job_id, "failed", result["message"])
            return self.fusion_repository.get_job(fusion_job_id)

        draft = self.fusion_repository.save_draft(
            fusion_job_id=fusion_job_id,
            chapter_id=job.chapter_id,
            fusion_id=f"fd_{uuid.uuid4().hex[:8]}",
            source_beat_ids=[beat.beat_id for beat in beat_drafts],
            plan_version=job.plan_version,
            state_lock_version=job.state_lock_version,
            text=result["text"],
            repeat_ratio=result["repeat_ratio"],
            facts_confirmed=result["facts_confirmed"],
            open_questions=result["open_questions"],
            end_state=result["end_state"],
            warnings=result["warnings"],
            status=result["status"],
        )
        self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "compose", result["status"], "fusion draft saved")
        self.fusion_repository.update_job_status(fusion_job_id, result["status"])
        return self.fusion_repository.get_job(fusion_job_id)

    def get_job(self, fusion_job_id: str):
        return self.fusion_repository.get_job(fusion_job_id)

    def get_logs(self, fusion_job_id: str):
        return self.fusion_repository.list_logs(fusion_job_id)

    def preview_from_job(self, fusion_job_id: str) -> Dict[str, Any]:
        job = self.get_job(fusion_job_id)
        if job is None:
            raise ValueError("Fusion job not found")
        return job.preview

    def _get_chapter(self, chapter_id: str):
        return self.chapter_repository.get_by_id(ChapterId(chapter_id))

    async def _load_beat_drafts(self, chapter_id: str, beat_ids: List[str]) -> List[BeatDraft]:
        beat_sheet = await self.beat_sheet_repository.get_by_chapter_id(chapter_id)
        if not beat_sheet or not beat_sheet.scenes:
            return []
        if len(beat_ids) != len(beat_sheet.scenes):
            raise ValueError("BeatDrafts do not match stored beat sheet")
        beats: List[BeatDraft] = []
        for index, beat_id in enumerate(beat_ids):
            scene = beat_sheet.scenes[index]
            beats.append(
                BeatDraft(
                    beat_id=beat_id,
                    title=scene.title,
                    function=scene.goal,
                    event=f"{scene.title}：{scene.goal}",
                    location=scene.location or "",
                    end_state={"location": scene.location} if scene.location else None,
                )
            )
        return beats

    def _compose_fusion(
        self,
        chapter_title: str,
        chapter_content: str,
        chapter_outline: str,
        beat_drafts: List[BeatDraft],
        target_words: int,
        suspense_budget: Dict[str, Any],
    ) -> Dict[str, Any]:
        unique_beats: List[BeatDraft] = []
        seen_signatures = set()
        warnings: List[str] = []
        duplicate_count = 0
        for beat in beat_drafts:
            signature = _norm_text(beat.event)
            if signature and signature in seen_signatures:
                duplicate_count += 1
                continue
            seen_signatures.add(signature)
            unique_beats.append(beat)
        if duplicate_count:
            warnings.append(f"发现 {duplicate_count} 个重复功能节拍，已合并")

        end_states = [b.end_state for b in unique_beats if b.end_state]
        normalized_end_states = {
            tuple(sorted((k, str(v)) for k, v in (state or {}).items()))
            for state in end_states
            if state
        }
        if len(normalized_end_states) > 1:
            return {
                "status": "failed",
                "message": "Output end state is not unique",
            }
        end_state = end_states[-1] if end_states else {}

        paragraphs: List[str] = []
        if chapter_title.strip():
            paragraphs.append(f"{chapter_title}。")
        if chapter_outline.strip():
            paragraphs.append(chapter_outline.strip())
        if chapter_content.strip():
            paragraphs.append(chapter_content.strip())

        last_location = ""
        facts_confirmed: List[str] = []
        open_questions: List[str] = []
        for beat in unique_beats:
            if beat.location and last_location and beat.location != last_location:
                paragraphs.append(f"随后，叙述自然过渡到{beat.location}。")
            if beat.location:
                last_location = beat.location
            paragraph = f"{beat.title}：{beat.event}"
            paragraphs.append(paragraph)
            facts_confirmed.append(beat.event)
            if beat.end_state:
                facts_confirmed.append("终态收束")

        text = "\n\n".join(paragraphs).strip()
        repeat_ratio = (duplicate_count / max(len(beat_drafts), 1))
        estimated_words = self._estimate_words(text)
        if target_words > 0 and estimated_words > target_words:
            cut = max(target_words, 1)
            text = text[:cut].rstrip()
            warnings.append("已按目标字数裁剪融合草稿")
        if repeat_ratio > 0.15:
            warnings.append("重复率偏高，建议回到 Beat 层继续去重")

        suspense_total = int(suspense_budget.get("primary") or 0) + int(suspense_budget.get("secondary") or 0)
        if suspense_total <= 0:
            open_questions.append("需要补足悬念预算")

        return {
            "status": "warning" if warnings else "completed",
            "text": text,
            "repeat_ratio": round(repeat_ratio, 2),
            "facts_confirmed": list(dict.fromkeys(facts_confirmed)),
            "open_questions": list(dict.fromkeys(open_questions)),
            "end_state": end_state,
            "warnings": warnings,
        }

    @staticmethod
    def _estimate_words(text: str) -> int:
        if not text.strip():
            return 0
        latin_tokens = re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?", text)
        cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
        punctuation = re.findall(r"[。！？?!,.，、；：\n\r\t ]", text)
        cjk_estimate = math.ceil(len(cjk_chars) / 2)
        baseline = len(latin_tokens) + cjk_estimate
        return max(1, baseline - len(punctuation) // 12)

    def _fail_job(self, fusion_job_id: str, chapter_id: str, step_name: str, message: str):
        self.fusion_repository.add_log(fusion_job_id, chapter_id, step_name, "failed", message)
        self.fusion_repository.update_job_status(fusion_job_id, "failed", message)
        return self.fusion_repository.get_job(fusion_job_id)
