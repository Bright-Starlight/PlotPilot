"""章节保存后的统一管线：质量门禁、叙事落库、向量检索、文风、图谱推断与后台抽取。

供 HTTP 保存、托管连写、自动驾驶审计复用，避免：
- 索引用正文截断 vs 叙事层用 LLM 总结 两套逻辑；
- 文风既入队 VOICE_ANALYSIS 又同步 score_chapter 重复计算。

顺序（重要产物均落库）：
0. 质量门禁：State Locks -> 融合草稿 -> Validation，全部通过后才继续
1. 分章叙事同步：一次 LLM 产出摘要/事件/埋线 + 三元组 + 伏笔 → StoryKnowledge + triples + ForeshadowingRegistry，再向量索引（chapter_narrative_sync）
2. 文风评分：写入 chapter_style_scores（仅一次，不再入队 VOICE_ANALYSIS）
3. 结构树知识图谱推断：KnowledgeGraphService.infer_from_chapter（与 LLM 三元组互补，非重复）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, TYPE_CHECKING

from domain.ai.services.llm_service import LLMService

if TYPE_CHECKING:
    from application.blueprint.services.beat_sheet_service import BeatSheetService
    from application.world.services.knowledge_service import KnowledgeService
    from application.core.services.chapter_fusion_service import ChapterFusionService
    from application.core.services.state_lock_service import StateLockService
    from domain.novel.repositories.novel_repository import NovelRepository

logger = logging.getLogger(__name__)


async def infer_kg_from_chapter(novel_id: str, chapter_number: int) -> bool:
    """结构树章节节点 → 知识图谱增量推断（与 HTTP 原 _try_infer_kg_chapter 一致）。"""
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
        from infrastructure.persistence.database.triple_repository import TripleRepository
        from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
        from application.world.services.knowledge_graph_service import KnowledgeGraphService

        db_path = get_db_path()
        kr = SqliteKnowledgeRepository(get_database())
        story_node_id = kr.find_story_node_id_for_chapter_number(novel_id, chapter_number)
        if not story_node_id:
            logger.debug("KG 推断跳过：章节 %d 无故事节点 novel=%s", chapter_number, novel_id)
            return True

        kg_service = KnowledgeGraphService(
            TripleRepository(),
            ChapterElementRepository(db_path),
            StoryNodeRepository(db_path),
        )
        triples = await kg_service.infer_from_chapter(story_node_id)
        logger.debug("KG 推断完成 novel=%s ch=%d 新三元组=%d", novel_id, chapter_number, len(triples))
        return True
    except Exception as e:
        logger.warning("KG 推断失败 novel=%s ch=%d: %s", novel_id, chapter_number, e)
        return False


class ChapterAftermathPipeline:
    """章节保存后分析与落库的统一入口。"""

    def __init__(
        self,
        knowledge_service: "KnowledgeService",
        chapter_indexing_service: Any,
        llm_service: LLMService,
        voice_drift_service: Any = None,
        triple_repository: Any = None,
        foreshadowing_repository: Any = None,
        storyline_repository: Any = None,
        chapter_repository: Any = None,
        plot_arc_repository: Any = None,
        narrative_event_repository: Any = None,
        novel_repository: Any = None,
        state_lock_service: "StateLockService | None" = None,
        chapter_fusion_service: "ChapterFusionService | None" = None,
        beat_sheet_service: "BeatSheetService | None" = None,
    ) -> None:
        self._knowledge = knowledge_service
        self._indexing = chapter_indexing_service
        self._llm = llm_service
        self._voice = voice_drift_service
        self._triple_repository = triple_repository
        self._foreshadowing_repository = foreshadowing_repository
        self._storyline_repository = storyline_repository
        self._chapter_repository = chapter_repository
        self._plot_arc_repository = plot_arc_repository
        self._narrative_event_repository = narrative_event_repository
        self._novel_repository = novel_repository
        self._state_lock_service = state_lock_service
        self._chapter_fusion_service = chapter_fusion_service
        self._beat_sheet_service = beat_sheet_service

    async def run_after_chapter_saved(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        *,
        run_quality_gate: bool = False,
        quality_gate_mode: str = "full",
        use_fusion_draft: bool = False,
    ) -> Dict[str, Any]:
        """保存正文后执行完整管线。返回文风结果供托管/审计门控使用。

        三元组与伏笔、故事线、张力、对话已在 narrative_sync 单次 LLM 中落库。

        Args:
            use_fusion_draft: 如果为 True，使用融合草稿文本而非正文进行信息同步
        """
        out: Dict[str, Any] = {
            "drift_alert": False,
            "similarity_score": None,
            "narrative_sync_ok": False,
            "voice_sync_ok": True,
            "kg_sync_ok": True,
            "local_sync_ok": False,
            "local_sync_errors": [],
            "quality_gate_passed": True,
        }

        if not content or not str(content).strip():
            logger.debug("aftermath 跳过：正文为空 novel=%s ch=%s", novel_id, chapter_number)
            out["local_sync_ok"] = True
            return out

        if run_quality_gate:
            gate_result = await self._run_quality_gate(
                novel_id,
                chapter_number,
                content,
                quality_gate_mode=quality_gate_mode,
            )
            out.update(gate_result)
            if not gate_result.get("quality_gate_passed", True):
                logger.warning(
                    "aftercare gate blocked novel=%s ch=%s step=%s reason=%s",
                    novel_id,
                    chapter_number,
                    gate_result.get("quality_gate_step", "unknown"),
                    gate_result.get("quality_gate_reason", "quality gate failed"),
                )
                return out

            # 门禁通过后，如果有融合草稿，使用融合草稿文本
            if use_fusion_draft and self._chapter_fusion_service is not None:
                chapter = self._resolve_chapter(novel_id, chapter_number)
                if chapter:
                    draft = self._chapter_fusion_service.fusion_repository.get_latest_draft_for_chapter(chapter.id)
                    if draft and draft.text:
                        content = draft.text
                        logger.info(
                            "使用融合草稿文本进行信息同步 novel=%s ch=%s fusion_id=%s",
                            novel_id, chapter_number, draft.fusion_id
                        )

        # 1) 叙事 + 向量 + 故事线 + 张力 + 对话（与 chapter_narrative_sync 一致）
        try:
            from application.world.services.chapter_narrative_sync import (
                sync_chapter_narrative_after_save,
            )

            await sync_chapter_narrative_after_save(
                novel_id,
                chapter_number,
                content,
                self._knowledge,
                self._indexing,
                self._llm,
                triple_repository=self._triple_repository,
                foreshadowing_repo=self._foreshadowing_repository,
                storyline_repository=self._storyline_repository,
                chapter_repository=self._chapter_repository,
                plot_arc_repository=self._plot_arc_repository,
                narrative_event_repository=self._narrative_event_repository,
            )
            out["narrative_sync_ok"] = True
        except Exception as e:
            logger.warning(
                "叙事同步/向量失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )
            out["local_sync_errors"].append(f"叙事同步失败: {e}")

        # 2) 文风（落库 chapter_style_scores）
        # 支持 LLM 模式（异步）和统计模式（同步）
        if self._voice:
            try:
                # 检查是否使用 LLM 模式
                if getattr(self._voice, "use_llm_mode", False):
                    vr = await self._voice.score_chapter_async(
                        novel_id=novel_id,
                        chapter_number=chapter_number,
                        content=content,
                    )
                else:
                    vr = self._voice.score_chapter(
                        novel_id=novel_id,
                        chapter_number=chapter_number,
                        content=content,
                    )
                out["drift_alert"] = bool(vr.get("drift_alert", False))
                out["similarity_score"] = vr.get("similarity_score")
                out["voice_mode"] = vr.get("mode", "statistics")
                logger.debug(
                    "文风评分完成 novel=%s ch=%s mode=%s drift=%s",
                    novel_id,
                    chapter_number,
                    out.get("voice_mode"),
                    out["drift_alert"],
                )
            except Exception as e:
                logger.warning("文风评分失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
                out["voice_sync_ok"] = False
                out["local_sync_errors"].append(f"文风评分失败: {e}")

        # 3) 结构树 KG 推断
        out["kg_sync_ok"] = await infer_kg_from_chapter(novel_id, chapter_number)
        if not out["kg_sync_ok"]:
            out["local_sync_errors"].append("知识图谱推断失败")

        out["local_sync_ok"] = bool(out["narrative_sync_ok"] and out["voice_sync_ok"] and out["kg_sync_ok"])

        return out

    async def _run_quality_gate(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        *,
        quality_gate_mode: str = "full",
    ) -> Dict[str, Any]:
        """按门禁模式执行最终质量门禁。

        full: State Locks -> 融合草稿 -> Validation
        retry: 融合草稿 -> Validation（复用当前 State Locks 版本，不再重新生成）
        """
        result: Dict[str, Any] = {
            "quality_gate_passed": True,
            "quality_gate_step": "pass",
            "quality_gate_reason": "",
            "quality_gate_blockers": [],
            "state_lock_version": None,
            "fusion_id": "",
            "validation_report_id": "",
            "quality_gate_mode": quality_gate_mode,
        }

        if self._state_lock_service is None and self._chapter_fusion_service is None:
            return result

        chapter = self._resolve_chapter(novel_id, chapter_number)
        if chapter is None:
            result.update(
                {
                    "quality_gate_passed": False,
                    "quality_gate_step": "chapter_lookup",
                    "quality_gate_reason": "Chapter not found for quality gate",
                    "quality_gate_blockers": ["章节不存在，无法执行质量门禁"],
                }
            )
            return result

        if quality_gate_mode not in {"full", "retry"}:
            result.update(
                {
                    "quality_gate_passed": False,
                    "quality_gate_step": "gate_mode",
                    "quality_gate_reason": f"Unsupported quality gate mode: {quality_gate_mode}",
                    "quality_gate_blockers": [f"Unsupported quality gate mode: {quality_gate_mode}"],
                }
            )
            return result

        if quality_gate_mode == "full" and self._state_lock_service is not None:
            try:
                snapshot = await self._state_lock_service.generate_state_locks(chapter.id)
                result["state_lock_version"] = int(getattr(snapshot, "version", 0) or 0)
                result["plan_version"] = int(getattr(snapshot, "plan_version", 0) or 0)
            except Exception as exc:
                result.update(
                    {
                        "quality_gate_passed": False,
                        "quality_gate_step": "state_locks",
                        "quality_gate_reason": str(exc),
                        "quality_gate_blockers": [f"State Locks 生成失败: {exc}"],
                    }
                )
                return result
        if quality_gate_mode == "retry":
            if self._chapter_fusion_service is None:
                result.update(
                    {
                        "quality_gate_passed": False,
                        "quality_gate_step": "fusion",
                        "quality_gate_reason": "Chapter fusion service is unavailable",
                        "quality_gate_blockers": ["融合草稿不可用，无法执行重试"],
                    }
                )
                return result

            draft = self._chapter_fusion_service.fusion_repository.get_latest_draft_for_chapter(chapter.id)
            if draft is None:
                result.update(
                    {
                        "quality_gate_passed": False,
                        "quality_gate_step": "validation",
                        "quality_gate_reason": "No fusion draft is available for retry",
                        "quality_gate_blockers": ["没有可用于重试的融合草稿"],
                    }
                )
                return result

            result["state_lock_version"] = int(getattr(draft, "state_lock_version", 0) or 0)
            result["plan_version"] = int(getattr(draft, "plan_version", 0) or 0)
            if result["state_lock_version"] <= 0:
                result.update(
                    {
                        "quality_gate_passed": False,
                        "quality_gate_step": "fusion",
                        "quality_gate_reason": "Fusion draft is missing a valid state_lock_version",
                        "quality_gate_blockers": ["融合草稿缺少有效的 state_lock_version"],
                    }
                )
                return result

        if self._chapter_fusion_service is not None and quality_gate_mode in {"full", "retry"}:
            try:
                beat_sheet_repo = getattr(self._chapter_fusion_service, "beat_sheet_repository", None)
                beat_sheet = await beat_sheet_repo.get_by_chapter_id(chapter.id) if beat_sheet_repo else None
                state_lock_version = int(result.get("state_lock_version") or 0)
                plan_version = int(result.get("plan_version") or 0)
                stored_state_lock_version = int(getattr(beat_sheet, "state_lock_version", 0) or 0) if beat_sheet else 0
                stored_plan_version = int(getattr(beat_sheet, "plan_version", 0) or 0) if beat_sheet else 0
                needs_refresh = (
                    beat_sheet is None
                    or not getattr(beat_sheet, "scenes", None)
                    or stored_state_lock_version != state_lock_version
                    or stored_plan_version != plan_version
                )

                if needs_refresh:
                    if self._beat_sheet_service is None:
                        raise ValueError("Beat sheet service is unavailable to refresh stale beat sheet")
                    outline_text = str(getattr(chapter, "outline", "") or getattr(chapter, "content", "") or "").strip()
                    if not outline_text:
                        raise ValueError("Chapter outline is required before beat sheet generation")
                    logger.info(
                        "quality gate beat sheet refresh novel=%s ch=%s plan_version=%s state_lock_version=%s stale=%s",
                        novel_id,
                        chapter_number,
                        plan_version,
                        state_lock_version,
                        stored_state_lock_version != state_lock_version or stored_plan_version != plan_version,
                    )
                    beat_sheet = await self._beat_sheet_service.generate_beat_sheet(
                        chapter_id=chapter.id,
                        outline=outline_text,
                        plan_version=plan_version or None,
                        state_lock_version=state_lock_version,
                    )

                if beat_sheet is None or not getattr(beat_sheet, "scenes", None):
                    raise ValueError("Beat sheet not found")

                beat_ids = [f"{chapter.id}-beat-{index + 1}" for index, _ in enumerate(beat_sheet.scenes)]
                target_words = self._resolve_target_words(novel_id)
                suspense_budget = {"primary": 0, "secondary": 0}
                state_lock_version = int(result.get("state_lock_version") or getattr(beat_sheet, "state_lock_version", 0) or 0)
                if state_lock_version <= 0:
                    raise ValueError("State lock version is required before fusion")

                job = self._chapter_fusion_service.create_job(
                    chapter_id=chapter.id,
                    plan_version=int(result.get("plan_version") or getattr(beat_sheet, "plan_version", 0) or 0),
                    state_lock_version=state_lock_version,
                    beat_ids=beat_ids,
                    target_words=target_words,
                    suspense_budget=suspense_budget,
                )
                job = await self._chapter_fusion_service.run_job(job.fusion_job_id)
                draft = getattr(job, "fusion_draft", None)
                if draft is None:
                    raise ValueError("Fusion draft was not created")

                result["fusion_id"] = draft.fusion_id
                result["fusion_job_id"] = job.fusion_job_id
                result["fusion_status"] = job.status

                validation_service = getattr(self._chapter_fusion_service, "validation_service", None)
                if validation_service is not None:
                    report_id = getattr(draft, "latest_validation_report_id", "") or ""
                    report = None
                    if report_id:
                        report = validation_service.get_report(report_id)
                    else:
                        report = await validation_service.auto_validate_fusion_draft(chapter.id, draft.fusion_id)
                        report_id = report.report_id
                    result["validation_report_id"] = report_id
                    result["validation_status"] = getattr(report, "status", "")
                    blocking_count = int(getattr(report, "blocking_issue_count", 0) or 0)
                    if blocking_count > 0:
                        result.update(
                            {
                                "quality_gate_passed": False,
                                "quality_gate_step": "validation",
                                "quality_gate_reason": f"{blocking_count} blocking issue(s) remain",
                                "quality_gate_blockers": [f"Validation 仍有 {blocking_count} 个阻断问题"],
                            }
                        )
                        return result
                else:
                    result["validation_status"] = "skipped"
            except Exception as exc:
                result.update(
                    {
                        "quality_gate_passed": False,
                        "quality_gate_step": "fusion",
                        "quality_gate_reason": str(exc),
                        "quality_gate_blockers": [f"融合草稿生成失败: {exc}"],
                    }
                )
                return result

        return result

    def _resolve_chapter(self, novel_id: str, chapter_number: int):
        if self._chapter_repository is None:
            return None
        try:
            from domain.novel.value_objects.novel_id import NovelId

            chapter = None
            if hasattr(self._chapter_repository, "get_by_novel_and_number"):
                chapter = self._chapter_repository.get_by_novel_and_number(NovelId(novel_id), chapter_number)
            if chapter is None and hasattr(self._chapter_repository, "list_by_novel"):
                chapters = self._chapter_repository.list_by_novel(NovelId(novel_id)) or []
                chapter = next((item for item in chapters if int(getattr(item, "number", 0) or 0) == int(chapter_number)), None)
            return chapter
        except Exception as exc:
            logger.warning("quality gate chapter lookup failed novel=%s ch=%s: %s", novel_id, chapter_number, exc)
            return None

    def _resolve_target_words(self, novel_id: str) -> int:
        if self._novel_repository is not None:
            try:
                from domain.novel.value_objects.novel_id import NovelId

                novel = self._novel_repository.get_by_id(NovelId(novel_id))
                if novel is not None:
                    return int(getattr(novel, "target_words_per_chapter", 3500) or 3500)
            except Exception as exc:
                logger.debug("quality gate target words fallback novel=%s: %s", novel_id, exc)
        return 3500
