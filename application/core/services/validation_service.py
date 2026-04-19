"""Chapter validation service."""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Sequence

from application.ai.structured_json_pipeline import parse_and_repair_json, sanitize_llm_output, validate_json_schema
from application.core.dtos.validation_dto import (
    ValidationIssueDTO,
    ValidationRepairPatchDTO,
    ValidationReportDTO,
    ValidationSpanDTO,
    ValidationTokenUsageDTO,
)
from application.core.state_lock_inference_contract import AliasMappingPayload
from application.core.services.state_lock_service import StateLockService
from application.world.services.bible_service import BibleService
from application.world.services.knowledge_service import KnowledgeService
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.chapter_id import ChapterId
from infrastructure.persistence.database.sqlite_chapter_fusion_repository import SqliteChapterFusionRepository
from infrastructure.persistence.database.sqlite_chapter_draft_binding_repository import SqliteChapterDraftBindingRepository
from infrastructure.persistence.database.sqlite_validation_repository import SqliteValidationRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

if TYPE_CHECKING:
    from domain.ai.services.llm_service import LLMService


logger = logging.getLogger(__name__)


@dataclass
class DraftContext:
    draft_type: str
    draft_id: str
    text: str
    end_state: Dict[str, Any]
    plan_version: int
    state_lock_version: int


class ValidationService:
    def __init__(
        self,
        *,
        chapter_repository: ChapterRepository,
        fusion_repository: SqliteChapterFusionRepository,
        state_lock_service: StateLockService,
        validation_repository: SqliteValidationRepository,
        chapter_draft_binding_repository: SqliteChapterDraftBindingRepository,
        story_node_repository: StoryNodeRepository,
        knowledge_service: KnowledgeService,
        bible_service: BibleService,
        llm_service: "LLMService | None" = None,
        aftermath_pipeline: Any = None,
    ):
        self.chapter_repository = chapter_repository
        self.fusion_repository = fusion_repository
        self.state_lock_service = state_lock_service
        self.validation_repository = validation_repository
        self.chapter_draft_binding_repository = chapter_draft_binding_repository
        self.story_node_repository = story_node_repository
        self.knowledge_service = knowledge_service
        self.bible_service = bible_service
        self.llm_service = llm_service
        self.aftermath_pipeline = aftermath_pipeline

    async def start_validation(
        self,
        chapter_id: str,
        *,
        draft_type: str,
        draft_id: str,
        plan_version: int | None = None,
        state_lock_version: int | None = None,
    ) -> ValidationReportDTO:
        logger.info(
            "validation start chapter_id=%s draft_type=%s draft_id=%s plan_version=%s state_lock_version=%s",
            chapter_id,
            draft_type,
            draft_id,
            plan_version,
            state_lock_version,
        )
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            raise ValueError("Chapter not found")

        draft = self._load_draft_context(
            chapter_id,
            draft_type=draft_type,
            draft_id=draft_id,
            plan_version=plan_version,
            state_lock_version=state_lock_version,
        )
        lock_snapshot = self.state_lock_service.load_version(chapter_id, draft.state_lock_version)
        if lock_snapshot is None:
            logger.warning(
                "validation rejected chapter_id=%s draft_type=%s draft_id=%s reason=missing_state_lock_version state_lock_version=%s",
                chapter_id,
                draft_type,
                draft_id,
                draft.state_lock_version,
            )
            raise ValueError("Referenced state_lock_version is missing or invalid")

        plan = self._get_chapter_plan(
            chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id),
            chapter_id,
            chapter.number,
        )
        knowledge = self.knowledge_service.get_knowledge(
            chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id)
        )
        bible = self.bible_service.get_bible_by_novel(
            chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id)
        )

        report = self.validation_repository.create_report(
            report_id=f"vr_{uuid.uuid4().hex[:8]}",
            chapter_id=chapter_id,
            novel_id=chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id),
            draft_type=draft_type,
            draft_id=draft_id,
            plan_version=draft.plan_version,
            state_lock_version=draft.state_lock_version,
        )
        logger.info(
            "validation report created report_id=%s chapter_id=%s draft_type=%s draft_id=%s plan_version=%s state_lock_version=%s",
            report.report_id,
            chapter_id,
            draft_type,
            draft_id,
            draft.plan_version,
            draft.state_lock_version,
        )
        token_usage = ValidationTokenUsageDTO()
        issues = await self._collect_issues(
            chapter_id=chapter_id,
            draft=draft,
            plan=plan,
            knowledge=knowledge,
            bible=bible,
            token_usage=token_usage,
        )
        for issue in issues:
            issue.report_id = report.report_id
            issue.chapter_id = chapter_id
        passed = not any(issue.blocking and issue.status != "resolved" for issue in issues)
        saved_report = self.validation_repository.save_report_result(
            report_id=report.report_id,
            status="completed",
            passed=passed,
            issues=issues,
            token_usage=token_usage,
        )
        logger.info(
            "validation finished report_id=%s chapter_id=%s total_issues=%s blocking_issues=%s passed=%s token_usage=%s/%s/%s",
            saved_report.report_id,
            chapter_id,
            len(saved_report.issues),
            saved_report.blocking_issue_count,
            saved_report.passed,
            saved_report.token_usage.input_tokens,
            saved_report.token_usage.output_tokens,
            saved_report.token_usage.total_tokens,
        )
        return saved_report

    async def auto_validate_fusion_draft(self, chapter_id: str, fusion_id: str) -> ValidationReportDTO:
        logger.info(
            "validation auto-triggered chapter_id=%s draft_type=fusion draft_id=%s",
            chapter_id,
            fusion_id,
        )
        return await self.start_validation(chapter_id, draft_type="fusion", draft_id=fusion_id)

    def get_report(self, report_id: str) -> ValidationReportDTO:
        report = self.validation_repository.get_report(report_id)
        if report is None:
            raise ValueError("Validation report not found")
        return report

    def get_latest_report(self, chapter_id: str, *, draft_type: str, draft_id: str | None = None) -> ValidationReportDTO:
        report = self.validation_repository.get_latest_report(
            chapter_id=chapter_id,
            draft_type=draft_type,
            draft_id=draft_id,
        )
        if report is None:
            raise ValueError("Validation report not found")
        return report

    def list_issues(
        self,
        *,
        novel_id: str | None = None,
        chapter_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> List[ValidationIssueDTO]:
        if severity == "P0" and status == "ignored":
            raise ValueError("Blocking P0 issues cannot be ignored")
        return self.validation_repository.list_issues(
            novel_id=novel_id,
            chapter_id=chapter_id,
            severity=severity,
            status=status,
        )

    def update_issue_status(self, issue_id: str, status: str) -> ValidationIssueDTO:
        logger.info("validation issue status update requested issue_id=%s status=%s", issue_id, status)
        if status not in {"unresolved", "resolved", "ignored"}:
            raise ValueError("Unsupported validation issue status")
        issue = self.validation_repository.get_issue(issue_id)
        if issue is None:
            raise ValueError("Validation issue not found")
        if issue.severity == "P0" and status == "ignored":
            logger.warning("validation issue ignore rejected issue_id=%s severity=P0", issue_id)
            raise ValueError("Blocking P0 issues cannot be ignored")
        updated = self.validation_repository.update_issue_status(issue_id, status)
        logger.info(
            "validation issue status updated issue_id=%s status=%s severity=%s",
            updated.issue_id,
            updated.status,
            updated.severity,
        )
        return updated

    async def build_repair_patch(self, issue_id: str) -> ValidationRepairPatchDTO:
        logger.info("validation repair patch requested issue_id=%s", issue_id)
        issue = self.validation_repository.get_issue(issue_id)
        if issue is None:
            raise ValueError("Validation issue not found")
        if not issue.suggest_patch:
            raise ValueError("This validation issue does not support repair patch suggestions")
        report = self.validation_repository.get_report(issue.report_id)
        if report is None:
            raise ValueError("Validation report not found")
        draft = self._load_draft_context(
            issue.chapter_id,
            draft_type=report.draft_type,
            draft_id=report.draft_id,
            plan_version=report.plan_version,
            state_lock_version=report.state_lock_version,
        )
        fallback = self._build_fallback_patch(issue, draft.text)
        if self.llm_service is None:
            return ValidationRepairPatchDTO(issue_id=issue_id, patch_text=fallback, source="heuristic")
        prompt = Prompt(
            system=(
                "你是小说修稿助手。"
                "请根据给定问题只输出一段可直接替换/插入正文的修订建议，不要解释。"
            ),
            user=(
                f"问题标题：{issue.title}\n"
                f"问题说明：{issue.message}\n"
                f"问题片段：{issue.spans[0].excerpt if issue.spans else draft.text[:240]}\n"
                f"正文上下文：\n{draft.text[:1800]}\n\n"
                "输出要求：1. 80-220 字；2. 直接给出修订后的正文片段；3. 优先修复事实冲突/终态偏差。"
            ),
        )
        try:
            result = await self.llm_service.generate(prompt, GenerationConfig(max_tokens=400, temperature=0.2))
            patch_text = str(getattr(result, "content", "") or "").strip()
        except Exception:
            patch_text = ""
        patch = ValidationRepairPatchDTO(
            issue_id=issue_id,
            patch_text=patch_text or fallback,
            source="llm" if patch_text else "heuristic",
        )
        logger.info("validation repair patch ready issue_id=%s source=%s", issue_id, patch.source)
        return patch

    async def ensure_publishable(self, chapter_id: str) -> ValidationReportDTO:
        logger.info("publish gate check start chapter_id=%s", chapter_id)
        draft = self.fusion_repository.get_latest_draft_for_chapter(chapter_id)
        if draft is None:
            raise ValueError("No fusion draft is available for publish validation")
        latest_report = self.validation_repository.get_latest_report(
            chapter_id=chapter_id,
            draft_type="fusion",
            draft_id=draft.fusion_id,
        )
        if (
            latest_report is None
            or latest_report.plan_version != draft.plan_version
            or latest_report.state_lock_version != draft.state_lock_version
        ):
            latest_report = await self.start_validation(
                chapter_id,
                draft_type="fusion",
                draft_id=draft.fusion_id,
                plan_version=draft.plan_version,
                state_lock_version=draft.state_lock_version,
            )
        if latest_report.blocking_issue_count > 0:
            logger.warning(
                "publish gate blocked chapter_id=%s report_id=%s blocking_issue_count=%s",
                chapter_id,
                latest_report.report_id,
                latest_report.blocking_issue_count,
            )
            raise ValueError("Publish blocked by unresolved blocking validation issues")
        logger.info(
            "publish gate passed chapter_id=%s report_id=%s blocking_issue_count=%s",
            chapter_id,
            latest_report.report_id,
            latest_report.blocking_issue_count,
        )
        return latest_report

    async def get_publish_gate_status(self, chapter_id: str) -> tuple[bool, ValidationReportDTO, List[ValidationIssueDTO]]:
        logger.info("publish gate status requested chapter_id=%s", chapter_id)
        draft = self.fusion_repository.get_latest_draft_for_chapter(chapter_id)
        if draft is None:
            raise ValueError("No fusion draft is available for publish validation")
        latest_report = self.validation_repository.get_latest_report(
            chapter_id=chapter_id,
            draft_type="fusion",
            draft_id=draft.fusion_id,
        )
        if (
            latest_report is None
            or latest_report.plan_version != draft.plan_version
            or latest_report.state_lock_version != draft.state_lock_version
        ):
            latest_report = await self.start_validation(
                chapter_id,
                draft_type="fusion",
                draft_id=draft.fusion_id,
                plan_version=draft.plan_version,
                state_lock_version=draft.state_lock_version,
            )
        blocking_issues = [
            issue for issue in latest_report.issues
            if issue.blocking and issue.status != "resolved"
        ]
        logger.info(
            "publish gate status resolved chapter_id=%s report_id=%s publishable=%s blocking_issues=%s",
            chapter_id,
            latest_report.report_id,
            len(blocking_issues) == 0,
            len(blocking_issues),
        )
        return (len(blocking_issues) == 0, latest_report, blocking_issues)

    async def manual_publish_fusion_draft(self, chapter_id: str) -> dict:
        """手动发布融合草稿到章节正文，并执行信息同步。

        用于 Validation 阶段 LLM 误判时，人工审阅后手动触发发布。
        执行与自动发布相同的逻辑：
        1. 获取融合草稿并替换章节正文
        2. 执行信息同步（叙事同步、向量索引、文风评分、知识图谱推断）

        Args:
            chapter_id: 章节 ID

        Returns:
            包含发布结果的字典

        Raises:
            ValueError: 如果章节不存在或没有融合草稿
        """
        logger.info("manual publish requested chapter_id=%s", chapter_id)

        # 获取章节实体
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            raise ValueError("Chapter not found")

        # 获取最新融合草稿
        draft = self.fusion_repository.get_latest_draft_for_chapter(chapter_id)
        if draft is None:
            raise ValueError("No fusion draft is available for manual publish")

        if not draft.text:
            raise ValueError("Fusion draft text is empty")

        # 将融合草稿写回章节实体
        chapter.update_content(draft.text)
        self.chapter_repository.save(chapter)
        self.chapter_draft_binding_repository.upsert_binding(
            chapter_id=chapter_id,
            novel_id=chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id),
            draft_type="merged",
            draft_id="merged-current",
            plan_version=int(draft.plan_version),
            state_lock_version=int(draft.state_lock_version),
            source_fusion_id=draft.fusion_id,
        )

        logger.info(
            "manual publish completed chapter_id=%s fusion_id=%s text_length=%s",
            chapter_id,
            draft.fusion_id,
            len(draft.text),
        )

        # 构建返回结果，包含信息同步状态
        result = {
            "chapter_id": chapter_id,
            "fusion_id": draft.fusion_id,
            "plan_version": draft.plan_version,
            "state_lock_version": draft.state_lock_version,
            "text_length": len(draft.text),
            "published": True,
            "info_sync_completed": False,
            "info_sync_error": None,
        }

        # 执行信息同步（与自动发布后的流程一致）
        if self.aftermath_pipeline is not None:
            try:
                logger.info(
                    "manual publish triggering info sync chapter_id=%s chapter_num=%s",
                    chapter_id,
                    chapter.number,
                )
                drift_result = await self.aftermath_pipeline.run_after_chapter_saved(
                    chapter.novel_id.value,
                    chapter.number,
                    draft.text,
                    run_quality_gate=False,  # 不再执行质量门禁（已通过人工审阅）
                    use_fusion_draft=True,   # 使用融合草稿
                )
                logger.info(
                    "manual publish info sync completed chapter_id=%s similarity=%s drift_alert=%s",
                    chapter_id,
                    drift_result.get("similarity_score"),
                    drift_result.get("drift_alert"),
                )
                result["info_sync_completed"] = True
            except Exception as e:
                logger.warning(
                    "manual publish info sync failed chapter_id=%s error=%s",
                    chapter_id,
                    e,
                )
                result["info_sync_error"] = str(e)
                # 信息同步失败不影响发布结果，仅记录警告
        else:
            logger.warning(
                "manual publish skipped info sync: aftermath_pipeline not available chapter_id=%s",
                chapter_id,
            )
            result["info_sync_error"] = "aftermath_pipeline not available"

        return result

    def _load_draft_context(
        self,
        chapter_id: str,
        *,
        draft_type: str,
        draft_id: str,
        plan_version: int | None,
        state_lock_version: int | None,
    ) -> DraftContext:
        if draft_type == "fusion":
            logger.info(
                "validation draft load chapter_id=%s draft_type=fusion draft_id=%s",
                chapter_id,
                draft_id,
            )
            draft = self.fusion_repository.get_draft(draft_id)
            if draft is None or draft.chapter_id != chapter_id:
                raise ValueError("Fusion draft not found")
            if plan_version is not None and int(plan_version) != int(draft.plan_version):
                raise ValueError("Validation must use the same plan_version as the fusion draft")
            if state_lock_version is not None and int(state_lock_version) != int(draft.state_lock_version):
                raise ValueError("Validation must use the same state_lock_version as the fusion draft")
            return DraftContext(
                draft_type="fusion",
                draft_id=draft_id,
                text=draft.text,
                end_state=draft.end_state,
                plan_version=draft.plan_version,
                state_lock_version=draft.state_lock_version,
            )

        if draft_type == "merged":
            logger.info(
                "validation draft load chapter_id=%s draft_type=merged draft_id=%s",
                chapter_id,
                draft_id,
            )
            chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
            if chapter is None:
                raise ValueError("Chapter not found")
            binding = self.chapter_draft_binding_repository.get_binding(
                chapter_id=chapter_id,
                draft_type="merged",
                draft_id=draft_id,
            )
            if binding is None and draft_id == "merged-current":
                binding = self.chapter_draft_binding_repository.get_latest_binding(
                    chapter_id=chapter_id,
                    draft_type="merged",
                )
            if binding is None:
                if plan_version is None or state_lock_version is None:
                    raise ValueError(
                        "Merged draft is not bound to a state_lock_version; save or validate it once with explicit plan_version and state_lock_version"
                    )
                if not self.state_lock_service.has_version(chapter_id, state_lock_version):
                    raise ValueError("Referenced state_lock_version is missing or invalid")
                binding = self.chapter_draft_binding_repository.upsert_binding(
                    chapter_id=chapter_id,
                    novel_id=chapter.novel_id.value if hasattr(chapter.novel_id, "value") else str(chapter.novel_id),
                    draft_type="merged",
                    draft_id=draft_id,
                    plan_version=int(plan_version),
                    state_lock_version=int(state_lock_version),
                )
                logger.info(
                    "validation merged binding seeded chapter_id=%s draft_id=%s plan_version=%s state_lock_version=%s",
                    chapter_id,
                    draft_id,
                    int(plan_version),
                    int(state_lock_version),
                )
            else:
                if plan_version is not None and int(plan_version) != int(binding.plan_version):
                    logger.warning(
                        "validation merged binding mismatch chapter_id=%s draft_id=%s field=plan_version requested=%s stored=%s",
                        chapter_id,
                        draft_id,
                        int(plan_version),
                        int(binding.plan_version),
                    )
                    raise ValueError("Merged draft plan_version does not match stored draft binding")
                if state_lock_version is not None and int(state_lock_version) != int(binding.state_lock_version):
                    logger.warning(
                        "validation merged binding mismatch chapter_id=%s draft_id=%s field=state_lock_version requested=%s stored=%s",
                        chapter_id,
                        draft_id,
                        int(state_lock_version),
                        int(binding.state_lock_version),
                    )
                    raise ValueError("Merged draft state_lock_version does not match stored draft binding")
                if not self.state_lock_service.has_version(chapter_id, binding.state_lock_version):
                    logger.warning(
                        "validation merged binding rejected chapter_id=%s draft_id=%s reason=missing_state_lock_version state_lock_version=%s",
                        chapter_id,
                        draft_id,
                        binding.state_lock_version,
                    )
                    raise ValueError("Referenced state_lock_version is missing or invalid")
                logger.info(
                    "validation merged binding reused chapter_id=%s draft_id=%s plan_version=%s state_lock_version=%s",
                    chapter_id,
                    draft_id,
                    int(binding.plan_version),
                    int(binding.state_lock_version),
                )
            return DraftContext(
                draft_type="merged",
                draft_id=draft_id,
                text=chapter.content or "",
                end_state={},
                plan_version=int(binding.plan_version),
                state_lock_version=int(binding.state_lock_version),
            )

        raise ValueError("Unsupported draft_type")

    async def _collect_issues(
        self,
        *,
        chapter_id: str,
        draft: DraftContext,
        plan: Any,
        knowledge: Any,
        bible: Any,
        token_usage: ValidationTokenUsageDTO,
    ) -> List[ValidationIssueDTO]:
        paragraphs = self._split_paragraphs(draft.text)
        issues: List[ValidationIssueDTO] = []
        issues.extend(self._detect_numeric_conflicts(paragraphs))
        issues.extend(
            self._convert_lock_violations(
                self.state_lock_service.evaluate_text_violations(
                    chapter_id,
                    draft.state_lock_version,
                    text=draft.text,
                    end_state=draft.end_state,
                ),
                paragraphs,
            )
        )
        issues.extend(self._detect_plan_end_state_mismatch(plan, draft, paragraphs))
        issues.extend(await self._run_semantic_checks(draft, bible, paragraphs, token_usage))
        return issues

    def _detect_numeric_conflicts(self, paragraphs: Sequence[str]) -> List[ValidationIssueDTO]:
        seen: Dict[str, set[str]] = {}
        spans: Dict[str, List[ValidationSpanDTO]] = {}
        for index, paragraph in enumerate(paragraphs):
            for match in re.finditer(r"([\u4e00-\u9fffA-Za-z]{2,16})(?:为|是|共|约|达|有)?(\d+(?:\.\d+)?(?:两|人|次|日|夜|年|月|%|张|件|个)?)", paragraph):
                label = match.group(1)
                value = match.group(2)
                seen.setdefault(label, set()).add(value)
                spans.setdefault(label, []).append(
                    ValidationSpanDTO(
                        paragraph_index=index,
                        start_offset=match.start(2),
                        end_offset=match.end(2),
                        excerpt=paragraph[:180],
                    )
                )
        issues: List[ValidationIssueDTO] = []
        for label, values in seen.items():
            if len(values) < 2:
                continue
            issues.append(
                ValidationIssueDTO(
                    issue_id=f"vi_{uuid.uuid4().hex[:8]}",
                    report_id="",
                    chapter_id="",
                    severity="P0",
                    code="numeric_conflict",
                    title="检测到互斥数值事实",
                    message=f"{label} 在同一草稿中出现多个互斥数值：{'、'.join(sorted(values))}",
                    spans=spans.get(label, []),
                    blocking=True,
                    suggest_patch=True,
                    metadata={"layer": "rule_detection", "field": label},
                )
            )
        return issues

    def _convert_lock_violations(
        self,
        violations: List[Dict[str, Any]],
        paragraphs: Sequence[str],
    ) -> List[ValidationIssueDTO]:
        issues: List[ValidationIssueDTO] = []
        for violation in violations:
            group = str(violation.get("group") or "")
            entry_key = str(violation.get("entry_key") or "")
            needle = self._span_needle(violation)
            spans = self._find_spans(paragraphs, needle)
            issues.append(
                ValidationIssueDTO(
                    issue_id=f"vi_{uuid.uuid4().hex[:8]}",
                    report_id="",
                    chapter_id="",
                    severity=str(violation.get("severity") or "P0"),
                    code=f"{group}_violation",
                    title=self._issue_title_for_group(group),
                    message=str(violation.get("message") or ""),
                    spans=spans,
                    blocking=True,
                    suggest_patch=group in {"numeric_lock", "ending_lock"},
                    metadata={
                        "layer": "state_comparison",
                        "group": group,
                        "entry_key": entry_key,
                    },
                )
            )
        return issues

    def _detect_plan_end_state_mismatch(
        self,
        plan: Any,
        draft: DraftContext,
        paragraphs: Sequence[str],
    ) -> List[ValidationIssueDTO]:
        if not draft.end_state:
            return []
        planned_end = str(getattr(plan, "timeline_end", "") or "").strip()
        actual_end = str(draft.end_state.get("location") or draft.end_state.get("state") or "").strip()
        if not planned_end or not actual_end or planned_end == actual_end:
            return []
        return [
            ValidationIssueDTO(
                issue_id=f"vi_{uuid.uuid4().hex[:8]}",
                report_id="",
                chapter_id="",
                severity="P0",
                code="planned_end_state_conflict",
                title="章节终态与规划不一致",
                message=f"规划要求终态为 {planned_end}，当前草稿终态为 {actual_end}",
                spans=self._find_spans(paragraphs, actual_end),
                blocking=True,
                suggest_patch=True,
                metadata={"layer": "plan_comparison"},
            )
        ]

    async def _run_semantic_checks(
        self,
        draft: DraftContext,
        bible: Any,
        paragraphs: Sequence[str],
        token_usage: ValidationTokenUsageDTO,
    ) -> List[ValidationIssueDTO]:
        if self.llm_service is None:
            return []
        aliases = self._collect_semantic_aliases(bible)
        normalized_text = draft.text.strip()
        if len(normalized_text) < 60 or len(paragraphs) < 1 or not aliases:
            logger.info(
                "validation semantic checks skipped draft_type=%s reason=insufficient_signal text_len=%s paragraph_count=%s alias_count=%s",
                draft.draft_type,
                len(normalized_text),
                len(paragraphs),
                len(aliases),
            )
            return []
        logger.info(
            "validation semantic checks running draft_type=%s text_len=%s paragraph_count=%s alias_count=%s",
            draft.draft_type,
            len(normalized_text),
            len(paragraphs),
            len(aliases),
        )
        prompt = Prompt(
            system=(
                "你是小说章节语义校验器。"
                "只输出一个 JSON 对象。"
                "只允许输出 identity_drift、alias_mismatch、role_conflict、pronoun_reference_error 这四类 code。"
                "若正文太短或证据不足，不要猜测。"
                "若未发现身份漂移或别名错配，issues 返回空数组。"
            ),
            user=(
                f"章节草稿类型：{draft.draft_type}\n"
                f"已知人物：{[item.model_dump() for item in aliases[:12]]}\n"
                f"正文：\n{normalized_text[:3000]}\n\n"
                "输出格式："
                "{\"issues\":[{\"severity\":\"P1\",\"code\":\"identity_drift\",\"title\":\"...\",\"message\":\"...\",\"needle\":\"正文中的短语\"}]}"
            ),
        )
        try:
            result = await self.llm_service.generate(prompt, GenerationConfig(max_tokens=800, temperature=0.1))
        except Exception:
            logger.warning("validation semantic checks failed draft_type=%s reason=llm_error", draft.draft_type)
            return []
        usage = getattr(result, "token_usage", None)
        if usage is not None:
            token_usage.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            token_usage.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            token_usage.total_tokens = token_usage.input_tokens + token_usage.output_tokens
        cleaned = sanitize_llm_output(result.content if hasattr(result, "content") else str(result))
        data, _ = parse_and_repair_json(cleaned)
        if not isinstance(data, dict):
            logger.warning("validation semantic checks failed draft_type=%s reason=invalid_json", draft.draft_type)
            return []
        raw_issues = data.get("issues")
        if not isinstance(raw_issues, list):
            logger.warning("validation semantic checks failed draft_type=%s reason=missing_issues_array", draft.draft_type)
            return []
        issues: List[ValidationIssueDTO] = []
        allowed_codes = {"identity_drift", "alias_mismatch", "role_conflict", "pronoun_reference_error"}
        for raw in raw_issues[:5]:
            if not isinstance(raw, dict):
                continue
            message = str(raw.get("message") or "").strip()
            if not message:
                continue
            code = str(raw.get("code") or "semantic_issue").strip() or "semantic_issue"
            if code not in allowed_codes:
                code = "identity_drift"
            needle = str(raw.get("needle") or "").strip()
            issues.append(
                ValidationIssueDTO(
                    issue_id=f"vi_{uuid.uuid4().hex[:8]}",
                    report_id="",
                    chapter_id="",
                    severity=str(raw.get("severity") or "P1"),
                    code=code,
                    title=str(raw.get("title") or "语义一致性问题"),
                    message=message,
                    spans=self._find_spans(paragraphs, needle),
                    blocking=False,
                    suggest_patch=False,
                    metadata={"layer": "semantic_judgment"},
                )
            )
        logger.info(
            "validation semantic checks completed draft_type=%s issues=%s input_tokens=%s output_tokens=%s",
            draft.draft_type,
            len(issues),
            token_usage.input_tokens,
            token_usage.output_tokens,
        )
        return issues

    @staticmethod
    def _collect_semantic_aliases(bible: Any) -> List[AliasMappingPayload]:
        characters = list(getattr(bible, "characters", []) or [])
        aliases: List[AliasMappingPayload] = []
        seen: set[tuple[str, str]] = set()
        for character in characters:
            canonical_name = str(getattr(character, "name", "") or "").strip()
            if not canonical_name:
                continue
            candidate_aliases = [canonical_name]
            raw_aliases = getattr(character, "aliases", None)
            if isinstance(raw_aliases, list):
                candidate_aliases.extend(str(item or "").strip() for item in raw_aliases)
            for alias in candidate_aliases:
                if not alias:
                    continue
                pair = (alias, canonical_name)
                if pair in seen:
                    continue
                seen.add(pair)
                aliases.append(AliasMappingPayload(alias=alias, canonical_name=canonical_name))
        return aliases

    @staticmethod
    def _span_needle(violation: Dict[str, Any]) -> str:
        message = str(violation.get("message") or "")
        if "：" in message:
            return message.split("：", 1)[-1].split("，", 1)[0].strip()
        if "应为 " in message:
            return message.split("应为 ", 1)[-1].split("，", 1)[0].strip()
        return ""

    @staticmethod
    def _issue_title_for_group(group: str) -> str:
        titles = {
            "character_lock": "违反人物禁入锁",
            "numeric_lock": "违反数值锁",
            "ending_lock": "违反终态锁",
        }
        return titles.get(group, "违反状态锁")

    @staticmethod
    def _build_fallback_patch(issue: ValidationIssueDTO, text: str) -> str:
        anchor = issue.spans[0].excerpt if issue.spans else text[:180]
        if issue.code == "planned_end_state_conflict" or issue.metadata.get("group") == "ending_lock":
            return f"建议将章末段落改写为与目标终态一致的落点，并保留原有情绪推进：\n{anchor[:120]}……随后人物抵达或确认进入目标地点/状态，形成与规划一致的收束。"
        if issue.code == "numeric_conflict" or issue.metadata.get("group") == "numeric_lock":
            return f"建议统一冲突数值，只保留一个版本并删除其余表述：\n{anchor[:120]}……将相关数字改写成同一口径，避免重复出现互斥值。"
        return f"建议围绕以下片段做最小修订以消除冲突：\n{anchor[:160]}"

    @staticmethod
    def _split_paragraphs(text: str) -> List[str]:
        parts = [segment.strip() for segment in re.split(r"\n+", text or "") if segment.strip()]
        return parts or ([text.strip()] if text.strip() else [])

    @staticmethod
    def _find_spans(paragraphs: Sequence[str], needle: str) -> List[ValidationSpanDTO]:
        if not paragraphs:
            return []
        if not needle:
            last = paragraphs[-1]
            return [
                ValidationSpanDTO(
                    paragraph_index=len(paragraphs) - 1,
                    start_offset=0,
                    end_offset=min(len(last), 180),
                    excerpt=last[:180],
                )
            ]
        spans: List[ValidationSpanDTO] = []
        for index, paragraph in enumerate(paragraphs):
            start = paragraph.find(needle)
            if start >= 0:
                spans.append(
                    ValidationSpanDTO(
                        paragraph_index=index,
                        start_offset=start,
                        end_offset=start + len(needle),
                        excerpt=paragraph[:180],
                    )
                )
        return spans

    def _get_chapter_plan(self, novel_id: str, chapter_id: str, chapter_number: int):
        nodes = self.story_node_repository.get_by_novel_sync(novel_id)
        for node in nodes:
            if node.id == chapter_id:
                return node
        for node in nodes:
            if getattr(node, "node_type", None).value == "chapter" and node.number == chapter_number:
                return node
        return type("PlanFallback", (), {"timeline_end": "", "outline": "", "description": ""})()
