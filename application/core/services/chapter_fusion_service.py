"""章节融合服务。"""
from __future__ import annotations

import math
import logging
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from application.ai.structured_json_pipeline import structured_json_generate
from application.core.chapter_fusion_contract import (
    FusionGenerationPayload,
    fusion_generation_response_format,
)
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.chapter_id import ChapterId
from infrastructure.persistence.database.sqlite_state_lock_repository import SqliteStateLockRepository
from infrastructure.persistence.database.sqlite_beat_sheet_repository import SqliteBeatSheetRepository
from infrastructure.persistence.database.sqlite_chapter_fusion_repository import SqliteChapterFusionRepository

if TYPE_CHECKING:
    from application.core.services.validation_service import ValidationService


logger = logging.getLogger(__name__)


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
        state_lock_repository: SqliteStateLockRepository,
        llm_service: LLMService,
        validation_service: Optional["ValidationService"] = None,
    ):
        self.chapter_repository = chapter_repository
        self.beat_sheet_repository = beat_sheet_repository
        self.fusion_repository = fusion_repository
        self.state_lock_repository = state_lock_repository
        self.llm_service = llm_service
        self.validation_service = validation_service

    def create_job(
        self,
        chapter_id: str,
        plan_version: int,
        state_lock_version: int,
        beat_ids: List[str],
        target_words: int,
        suspense_budget: Dict[str, Any],
    ):
        logger.info(
            "fusion job create requested chapter_id=%s plan_version=%s state_lock_version=%s beat_count=%s target_words=%s",
            chapter_id,
            plan_version,
            state_lock_version,
            len(beat_ids),
            target_words,
        )
        chapter = self._get_chapter(chapter_id)
        if chapter is None:
            raise ValueError("Chapter not found")
        if plan_version <= 0:
            raise ValueError("plan_version is required")
        if state_lock_version <= 0:
            raise ValueError("state_lock_version is required")
        if not beat_ids:
            raise ValueError("BeatDrafts are required")
        if not self.state_lock_repository.has_version(chapter_id, state_lock_version):
            raise ValueError("State locks must be generated before fusion can run")

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
        logger.info(
            "fusion job created job_id=%s chapter_id=%s plan_version=%s state_lock_version=%s beat_count=%s",
            job_id,
            chapter_id,
            plan_version,
            state_lock_version,
            len(beat_ids),
        )
        return job

    async def run_job(self, fusion_job_id: str):
        logger.info("fusion job run start job_id=%s", fusion_job_id)
        job = self.fusion_repository.get_job(fusion_job_id)
        if job is None:
            raise ValueError("Fusion job not found")
        self.fusion_repository.update_job_status(fusion_job_id, "running")
        self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "validate", "running", "validating inputs")
        logger.info(
            "fusion job validating job_id=%s chapter_id=%s plan_version=%s state_lock_version=%s beat_count=%s",
            fusion_job_id,
            job.chapter_id,
            job.plan_version,
            job.state_lock_version,
            len(job.beat_ids),
        )

        chapter = self._get_chapter(job.chapter_id)
        if chapter is None:
            return self._fail_job(job.fusion_job_id, job.chapter_id, "chapter_missing", "Chapter not found")
        state_lock_snapshot = self.state_lock_repository.get_version_by_chapter(job.chapter_id, job.state_lock_version)
        if state_lock_snapshot is None:
            logger.warning(
                "fusion job validation failed job_id=%s chapter_id=%s reason=missing_state_lock_version state_lock_version=%s",
                fusion_job_id,
                job.chapter_id,
                job.state_lock_version,
            )
            return self._fail_job(
                job.fusion_job_id,
                job.chapter_id,
                "state_lock_missing",
                "Referenced state_lock_version is missing or invalid",
            )

        try:
            beat_drafts = await self._load_beat_drafts_with_lock(
                job.chapter_id,
                job.beat_ids,
                state_lock_version=job.state_lock_version,
            )
        except ValueError as exc:
            self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "validate", "failed", str(exc))
            logger.warning(
                "fusion job validation failed job_id=%s chapter_id=%s reason=beat_drafts_invalid error=%s",
                fusion_job_id,
                job.chapter_id,
                str(exc),
            )
            return self._fail_job(job.fusion_job_id, job.chapter_id, "beats_invalid", str(exc))
        if not beat_drafts:
            logger.warning(
                "fusion job validation failed job_id=%s chapter_id=%s reason=beats_missing",
                fusion_job_id,
                job.chapter_id,
            )
            return self._fail_job(job.fusion_job_id, job.chapter_id, "beats_missing", "BeatDrafts are missing")

        logger.info(
            "fusion job compose start job_id=%s chapter_id=%s beat_count=%s state_lock_version=%s",
            fusion_job_id,
            job.chapter_id,
            len(beat_drafts),
            job.state_lock_version,
        )
        result = await self._compose_fusion(
            chapter.title,
            chapter.content or "",
            chapter.outline or "",
            beat_drafts,
            job.target_words,
            job.suspense_budget.__dict__,
            state_lock_snapshot.locks,
        )
        if result["status"] == "failed":
            self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "compose", "failed", result["message"])
            logger.warning(
                "fusion job compose failed job_id=%s chapter_id=%s message=%s",
                fusion_job_id,
                job.chapter_id,
                result["message"],
            )
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
            state_lock_violations=result["state_lock_violations"],
            status=result["status"],
        )
        self.fusion_repository.add_log(fusion_job_id, job.chapter_id, "compose", result["status"], "fusion draft saved")
        logger.info(
            "fusion job compose saved job_id=%s chapter_id=%s fusion_id=%s status=%s repeat_ratio=%s warning_count=%s state_lock_violation_count=%s",
            fusion_job_id,
            job.chapter_id,
            draft.fusion_id,
            result["status"],
            result["repeat_ratio"],
            len(result["warnings"]),
            len(result["state_lock_violations"]),
        )
        self.fusion_repository.update_job_status(fusion_job_id, result["status"])
        if self.validation_service is not None:
            try:
                logger.info(
                    "fusion job validation trigger job_id=%s chapter_id=%s fusion_id=%s",
                    fusion_job_id,
                    job.chapter_id,
                    draft.fusion_id,
                )
                report = await self.validation_service.auto_validate_fusion_draft(job.chapter_id, draft.fusion_id)
                self.fusion_repository.add_log(
                    fusion_job_id,
                    job.chapter_id,
                    "validation",
                    report.status,
                    f"validation report generated: {report.report_id}",
                )
                logger.info(
                    "fusion job validation completed job_id=%s chapter_id=%s report_id=%s report_status=%s blocking_issue_count=%s",
                    fusion_job_id,
                    job.chapter_id,
                    report.report_id,
                    report.status,
                    report.blocking_issue_count,
                )
            except ValueError as exc:
                self.fusion_repository.add_log(
                    fusion_job_id,
                    job.chapter_id,
                    "validation",
                    "failed",
                    str(exc),
                )
                logger.warning(
                    "fusion job validation failed job_id=%s chapter_id=%s error=%s",
                    fusion_job_id,
                    job.chapter_id,
                    str(exc),
                )
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
        return await self._load_beat_drafts_with_lock(chapter_id, beat_ids, state_lock_version=None)

    async def _load_beat_drafts_with_lock(
        self,
        chapter_id: str,
        beat_ids: List[str],
        *,
        state_lock_version: int | None,
    ) -> List[BeatDraft]:
        logger.info(
            "fusion beat drafts load start chapter_id=%s requested_state_lock_version=%s beat_count=%s",
            chapter_id,
            state_lock_version,
            len(beat_ids),
        )
        beat_sheet = await self.beat_sheet_repository.get_by_chapter_id(chapter_id)
        if not beat_sheet or not beat_sheet.scenes:
            logger.warning("fusion beat drafts load failed chapter_id=%s reason=beat_sheet_missing", chapter_id)
            return []
        beat_sheet_lock_version = int(getattr(beat_sheet, "state_lock_version", 0) or 0)
        if state_lock_version is not None:
            if beat_sheet_lock_version <= 0:
                logger.warning(
                    "fusion beat drafts load failed chapter_id=%s reason=beat_sheet_unbound requested_state_lock_version=%s",
                    chapter_id,
                    state_lock_version,
                )
                raise ValueError("BeatDrafts are not bound to a valid state_lock_version")
            if beat_sheet_lock_version != int(state_lock_version):
                logger.warning(
                    "fusion beat drafts load failed chapter_id=%s reason=state_lock_version_mismatch requested_state_lock_version=%s stored_state_lock_version=%s",
                    chapter_id,
                    state_lock_version,
                    beat_sheet_lock_version,
                )
                raise ValueError("BeatDrafts do not match requested state_lock_version")
        if len(beat_ids) != len(beat_sheet.scenes):
            logger.warning(
                "fusion beat drafts load failed chapter_id=%s reason=beat_count_mismatch requested=%s stored=%s",
                chapter_id,
                len(beat_ids),
                len(beat_sheet.scenes),
            )
            raise ValueError("BeatDrafts do not match stored beat sheet")
        beats: List[BeatDraft] = []
        for index, beat_id in enumerate(beat_ids):
            scene = beat_sheet.scenes[index]
            end_state = {"location": scene.location} if index == len(beat_ids) - 1 and scene.location else None
            beats.append(
                BeatDraft(
                    beat_id=beat_id,
                    title=scene.title,
                    function=scene.goal,
                    event=f"{scene.title}：{scene.goal}",
                    location=scene.location or "",
                    end_state=end_state,
                )
            )
        logger.info(
            "fusion beat drafts load completed chapter_id=%s beat_count=%s state_lock_version=%s",
            chapter_id,
            len(beats),
            beat_sheet_lock_version,
        )
        return beats

    async def _compose_fusion(
        self,
        chapter_title: str,
        chapter_content: str,
        chapter_outline: str,
        beat_drafts: List[BeatDraft],
        target_words: int,
        suspense_budget: Dict[str, Any],
        state_locks: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.info(
            "fusion compose start beat_count=%s target_words=%s suspense_primary=%s suspense_secondary=%s state_lock_group_count=%s",
            len(beat_drafts),
            target_words,
            int(suspense_budget.get("primary") or 0),
            int(suspense_budget.get("secondary") or 0),
            len(state_locks or {}),
        )
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
            logger.info("fusion compose deduplicated duplicate_count=%s", duplicate_count)

        end_states = [b.end_state for b in unique_beats if b.end_state]
        normalized_end_states = {
            tuple(sorted((k, str(v)) for k, v in (state or {}).items()))
            for state in end_states
            if state
        }
        if len(normalized_end_states) > 1:
            logger.warning("fusion compose failed reason=conflicting_end_states unique_end_state_count=%s", len(normalized_end_states))
            return {
                "status": "failed",
                "message": "Output end state is not unique",
            }
        end_state = end_states[-1] if end_states else {}

        required_facts = [beat.event for beat in unique_beats]
        prompt = self._build_fusion_prompt(
            chapter_title=chapter_title,
            chapter_content=chapter_content,
            chapter_outline=chapter_outline,
            beat_drafts=unique_beats,
            required_facts=required_facts,
            expected_end_state=end_state,
            suspense_budget=suspense_budget,
            target_words=target_words,
            state_locks=state_locks or {},
        )
        payload = await structured_json_generate(
            llm=self.llm_service,
            prompt=prompt,
            config=GenerationConfig(
                max_tokens=4096,
                temperature=0.6,
                response_format=fusion_generation_response_format(),
            ),
            schema_model=FusionGenerationPayload,
        )
        if payload is None:
            logger.warning("fusion compose failed reason=llm_payload_missing")
            return {
                "status": "failed",
                "message": "Fusion generation failed",
            }

        text = payload.text.strip()
        if not text:
            logger.warning("fusion compose failed reason=empty_text")
            return {
                "status": "failed",
                "message": "Fusion draft is empty",
            }

        warnings.extend(payload.model_warnings)
        facts_confirmed = self._resolve_confirmed_facts(required_facts, payload.facts_used)
        missing_facts = [fact for fact in required_facts if fact not in facts_confirmed]
        if missing_facts:
            preview = "；".join(missing_facts[:3])
            warnings.append(f"融合稿缺失 {len(missing_facts)} 条关键事实：{preview}")
            logger.warning("fusion compose missing_facts count=%s", len(missing_facts))

        open_questions: List[str] = list(dict.fromkeys(payload.open_questions))
        if end_state and payload.end_state and self._normalize_state(payload.end_state) != self._normalize_state(end_state):
            logger.warning("fusion compose failed reason=end_state_conflict")
            return {
                "status": "failed",
                "message": "Output end state conflicts with beat constraints",
            }
        end_state = payload.end_state or end_state
        state_lock_violations = self._collect_state_lock_violations(state_locks or {}, text, end_state)
        if state_lock_violations:
            warnings.append(state_lock_violations[0]["message"])
        repeat_ratio = (duplicate_count / max(len(beat_drafts), 1))
        estimated_words = self._estimate_words(text)
        if target_words > 0 and estimated_words > target_words:
            text = self._trim_to_target_words(text, target_words)
            warnings.append("已按目标字数裁剪融合草稿")
            logger.info(
                "fusion compose trimmed to target_words=%s estimated_words=%s",
                target_words,
                estimated_words,
            )
        if repeat_ratio > 0.15:
            warnings.append("重复率偏高，建议回到 Beat 层继续去重")
            logger.info("fusion compose repeat_ratio_high repeat_ratio=%s", round(repeat_ratio, 2))

        suspense_total = int(suspense_budget.get("primary") or 0) + int(suspense_budget.get("secondary") or 0)
        if suspense_total <= 0:
            open_questions.append("需要补足悬念预算")
        elif payload.suspense_used < suspense_total:
            warnings.append(f"悬念预算未完全覆盖，目标 {suspense_total}，实际 {payload.suspense_used}")
            logger.info(
                "fusion compose suspense_budget_partial target=%s used=%s",
                suspense_total,
                payload.suspense_used,
            )

        logger.info(
            "fusion compose completed status=%s repeat_ratio=%s fact_count=%s open_question_count=%s warning_count=%s state_lock_violation_count=%s",
            "warning" if warnings else "completed",
            round(repeat_ratio, 2),
            len(facts_confirmed),
            len(open_questions),
            len(warnings),
            len(state_lock_violations),
        )
        return {
            "status": "warning" if warnings else "completed",
            "text": text,
            "repeat_ratio": round(repeat_ratio, 2),
            "facts_confirmed": list(dict.fromkeys(facts_confirmed)),
            "open_questions": list(dict.fromkeys(open_questions)),
            "end_state": end_state,
            "warnings": warnings,
            "state_lock_violations": state_lock_violations,
        }

    def _build_fusion_prompt(
        self,
        chapter_title: str,
        chapter_content: str,
        chapter_outline: str,
        beat_drafts: List[BeatDraft],
        required_facts: List[str],
        expected_end_state: Dict[str, Any],
        suspense_budget: Dict[str, Any],
        target_words: int,
        state_locks: Dict[str, Any],
    ) -> Prompt:
        beat_lines = []
        for index, beat in enumerate(beat_drafts, start=1):
            beat_lines.append(
                (
                    f"{index}. 标题：{beat.title}\n"
                    f"   作用：{beat.function}\n"
                    f"   事件：{beat.event}\n"
                    f"   地点：{beat.location or '未指定'}\n"
                    f"   终态：{beat.end_state or {}}"
                )
            )
        fact_lines = "\n".join(f"- {fact}" for fact in required_facts) or "- 无"
        state_lock_lines = self._format_state_locks(state_locks)
        system_prompt = (
            "你是长篇小说章节融合编辑。"
            "你的任务是把节拍草稿融合成自然、连贯、可继续润色的章节正文。"
            "不要输出条目式标题，不要写“节拍一/节拍二”，正文必须是小说自然段。"
            "必须覆盖全部关键事实，保持人物关系与终态约束，不要编造输入里没有的新设定。"
            "只输出符合 JSON schema 的对象。"
        )
        user_prompt = (
            "任务代号：fusion_generation_v1\n\n"
            f"章节标题：{chapter_title or '未命名章节'}\n"
            f"目标字数：{target_words}\n"
            f"悬念预算：主悬念 {int(suspense_budget.get('primary') or 0)}，支悬念 {int(suspense_budget.get('secondary') or 0)}\n"
            f"预期终态：{expected_end_state or {}}\n\n"
            f"章节大纲：\n{chapter_outline or '无'}\n\n"
            f"现有正文（可吸收但不要原样拼贴）：\n{chapter_content or '无'}\n\n"
            f"节拍草稿：\n{'\n\n'.join(beat_lines)}\n\n"
            f"必保留事实：\n{fact_lines}\n\n"
            f"状态锁：\n{state_lock_lines}\n\n"
            "输出要求：\n"
            "1. text 必须是自然正文，避免“标题：内容”的模板痕迹。\n"
            "2. facts_used 必须逐条列出已覆盖的关键事实，文本内容需与输入事实一致。\n"
            "3. end_state 只填写正文最终收束状态；若输入没有终态可返回空对象。\n"
            "4. suspense_used 填写正文实际保留的悬念数量。\n"
            "5. open_questions 仅列出正文仍未解决的问题。\n"
            "6. model_warnings 仅列出你无法完全满足的约束。"
        )
        return Prompt(system=system_prompt, user=user_prompt)

    @staticmethod
    def _format_state_locks(state_locks: Dict[str, Any]) -> str:
        lines: List[str] = []
        for group_name, group in (state_locks or {}).items():
            entries = group.get("entries", []) if isinstance(group, dict) else []
            if not entries:
                continue
            lines.append(f"{group_name}:")
            for entry in entries:
                lines.append(f"- {entry.get('label')}: {entry.get('value')}")
        return "\n".join(lines) if lines else "- 无"

    @staticmethod
    def _collect_state_lock_violations(
        state_locks: Dict[str, Any],
        text: str,
        end_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        content = text or ""
        for entry in (state_locks.get("character_lock", {}) or {}).get("entries", []):
            if entry.get("kind") == "forbidden_character":
                name = str(entry.get("value") or "").strip()
                if name and name in content:
                    violations.append(
                        {"group": "character_lock", "message": f"正文包含被禁止人物：{name}"}
                    )
        for entry in (state_locks.get("numeric_lock", {}) or {}).get("entries", []):
            label = str(entry.get("label") or "").strip()
            value = str(entry.get("value") or "").strip()
            if label and value and label in content and value not in content:
                violations.append(
                    {"group": "numeric_lock", "message": f"{label} 与状态锁数值 {value} 不一致"}
                )
        ending_entries = (state_locks.get("ending_lock", {}) or {}).get("entries", [])
        if ending_entries:
            expected_end = str(ending_entries[0].get("value") or "").strip()
            actual_end = str(end_state.get("location") or end_state.get("state") or "").strip()
            if expected_end and actual_end and expected_end != actual_end:
                violations.append(
                    {"group": "ending_lock", "message": f"终态偏离状态锁：应为 {expected_end}，实际为 {actual_end}"}
                )
        return violations

    @staticmethod
    def _normalize_state(state: Dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((key, str(value)) for key, value in (state or {}).items()))

    @staticmethod
    def _resolve_confirmed_facts(required_facts: List[str], facts_used: List[str]) -> List[str]:
        used_map = {_norm_text(fact): fact for fact in facts_used if fact}
        confirmed: List[str] = []
        for fact in required_facts:
            if _norm_text(fact) in used_map:
                confirmed.append(fact)
        return list(dict.fromkeys(confirmed))

    def _trim_to_target_words(self, text: str, target_words: int) -> str:
        if target_words <= 0 or self._estimate_words(text) <= target_words:
            return text

        sentences = [segment.strip() for segment in re.split(r"(?<=[。！？!?])", text) if segment.strip()]
        kept: List[str] = []
        for sentence in sentences:
            candidate = "".join(kept + [sentence]).strip()
            if kept and self._estimate_words(candidate) > target_words:
                break
            kept.append(sentence)
        trimmed = "".join(kept).strip() or text.strip()
        while len(trimmed) > 1 and self._estimate_words(trimmed) > target_words:
            trimmed = trimmed[:-1].rstrip()
        return trimmed

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
        logger.warning(
            "fusion job failed job_id=%s chapter_id=%s step=%s message=%s",
            fusion_job_id,
            chapter_id,
            step_name,
            message,
        )
        self.fusion_repository.add_log(fusion_job_id, chapter_id, step_name, "failed", message)
        self.fusion_repository.update_job_status(fusion_job_id, "failed", message)
        return self.fusion_repository.get_job(fusion_job_id)
