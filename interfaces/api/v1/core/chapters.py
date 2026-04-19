"""Chapter API 路由"""
import logging
from typing import Any, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.core.services.chapter_service import ChapterService
from application.core.services.validation_service import ValidationService
from application.core.services.novel_service import NovelService
from application.core.dtos.chapter_dto import ChapterDTO
from application.core.dtos.novel_dto import NovelDTO
from application.audit.dtos.chapter_review_dto import ChapterReviewDTO
from application.core.dtos.chapter_structure_dto import ChapterStructureDTO
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from interfaces.api.dependencies import (
    get_chapter_service,
    get_novel_service,
    get_chapter_aftermath_pipeline,
    get_validation_service,
)
from domain.shared.exceptions import EntityNotFoundError
logger = logging.getLogger(__name__)


router = APIRouter(tags=["chapters"])


class ChapterDraftBindingRequest(BaseModel):
    """正文草稿绑定请求。"""
    draft_type: Literal["merged", "patch"] = Field(default="merged", description="正文草稿类型")
    draft_id: str = Field(default="merged-current", min_length=1, description="正文草稿标识")
    plan_version: int = Field(..., gt=0, description="绑定的规划版本")
    state_lock_version: int = Field(..., gt=0, description="绑定的状态锁版本")
    source_fusion_id: str | None = Field(default=None, description="可选来源融合稿 ID")


class UpdateChapterContentRequest(BaseModel):
    """更新章节内容请求"""
    content: str = Field(..., min_length=0, max_length=100000, description="章节内容")
    generation_metrics: dict | None = Field(default=None, description="可选的生成质量控制指标")
    draft_binding: ChapterDraftBindingRequest | None = Field(default=None, description="可选的正文草稿绑定信息")


class SaveChapterReviewRequest(BaseModel):
    """保存章节审阅请求"""
    status: Literal["draft", "reviewed", "approved"] = Field(..., description="审阅状态")
    memo: str = Field(default="", description="审阅备注")


class ChapterReviewResponse(BaseModel):
    """章节审阅响应"""
    status: str
    memo: str
    created_at: str
    updated_at: str


class ChapterStructureResponse(BaseModel):
    """章节结构响应"""
    word_count: int
    paragraph_count: int
    dialogue_ratio: float
    scene_count: int
    pacing: str


class ChapterGenerationMetricsResponse(BaseModel):
    novel_id: str
    chapter_number: int
    generated_via: str
    target: int
    actual: int
    tolerance: float
    delta: int
    status: str
    within_tolerance: bool
    action: str
    expansion_attempts: int
    trim_applied: bool
    fallback_used: bool
    beat_quality: list[dict[str, Any]] | None = None
    min_allowed: int
    max_allowed: int
    created_at: str | None = None
    updated_at: str | None = None


class ChapterAftermathStatusResponse(BaseModel):
    narrative_sync_ok: bool
    voice_sync_ok: bool
    kg_sync_ok: bool
    local_sync_ok: bool
    local_sync_errors: list[str] = Field(default_factory=list)
    drift_alert: bool = False
    similarity_score: float | None = None


class UpdateChapterResponse(BaseModel):
    id: str
    novel_id: str
    number: int
    title: str
    content: str
    word_count: int
    status: str
    aftermath: ChapterAftermathStatusResponse


class CreateChapterRequest(BaseModel):
    """创建章节请求"""
    chapter_id: str = Field(..., description="章节 ID")
    number: int = Field(..., gt=0, description="章节编号")
    title: str = Field(..., min_length=1, max_length=200, description="章节标题")
    content: str = Field(..., min_length=1, description="章节内容")


class EnsureChapterRequest(BaseModel):
    """确保章节存在请求（可选 title，不传则用「第N章」）"""
    title: str = Field(default="", max_length=200, description="章节标题（可选）")


# Routes
@router.get("/{novel_id}/chapters", response_model=List[ChapterDTO])
async def list_chapters(
    novel_id: str,
    service: ChapterService = Depends(get_chapter_service)
):
    """列出小说的所有章节

    Args:
        novel_id: 小说 ID
        service: Chapter 服务

    Returns:
        章节 DTO 列表
    """
    return service.list_chapters_by_novel(novel_id)


@router.post("/{novel_id}/chapters", response_model=NovelDTO, status_code=201)
async def create_chapter(
    novel_id: str,
    request: CreateChapterRequest,
    novel_service: NovelService = Depends(get_novel_service)
):
    """创建章节

    Args:
        novel_id: 小说 ID
        request: 创建章节请求
        novel_service: Novel 服务

    Returns:
        更新后的小说 DTO
    """
    try:
        return novel_service.add_chapter(
            novel_id=novel_id,
            chapter_id=request.chapter_id,
            number=request.number,
            title=request.title,
            content=request.content
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/chapters/{chapter_number}", response_model=ChapterDTO)
async def get_chapter(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节详情

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节 DTO

    Raises:
        HTTPException: 如果章节不存在
    """
    chapter = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter not found: {novel_id}/chapter-{chapter_number}"
        )
    return chapter


@router.post("/{novel_id}/chapters/{chapter_number}/ensure", response_model=ChapterDTO)
async def ensure_chapter(
    novel_id: str,
    request: EnsureChapterRequest,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """确保章节在正文库中存在；若不存在则创建空白记录（不校验章节号连续性）。

    适用于结构树手动添加章节节点后、用户点击想直接开始写作的场景。
    """
    return service.ensure_chapter(novel_id, chapter_number, request.title)


def _rollback_chapter_content(service: ChapterService, novel_id: str, chapter_number: int, original_content: str) -> None:
    try:
        service.update_chapter_by_novel_and_number(
            novel_id,
            chapter_number,
            original_content,
        )
    except Exception as exc:
        logger.error(
            "chapter rollback failed novel_id=%s chapter_number=%s error=%s",
            novel_id,
            chapter_number,
            exc,
        )


def _resolve_latest_fusion_draft_binding(
    service: ChapterService,
    pipeline: ChapterAftermathPipeline,
    chapter: ChapterDTO,
    explicit_binding: ChapterDraftBindingRequest | None,
) -> dict[str, Any] | None:
    if explicit_binding is not None:
        return explicit_binding.model_dump()

    fusion_service = getattr(pipeline, "_chapter_fusion_service", None)
    fusion_repository = getattr(fusion_service, "fusion_repository", None)
    if fusion_repository is None:
        return None

    draft = fusion_repository.get_latest_draft_for_chapter(chapter.id)
    if draft is None:
        return None

    return {
        "draft_type": "merged",
        "draft_id": "merged-current",
        "plan_version": int(draft.plan_version),
        "state_lock_version": int(draft.state_lock_version),
        "source_fusion_id": draft.fusion_id,
    }


def _persist_chapter_draft_binding(
    service: ChapterService,
    novel_id: str,
    chapter: ChapterDTO,
    draft_binding: dict[str, Any] | None,
) -> None:
    if not draft_binding:
        return

    repository = getattr(service, "chapter_draft_binding_repository", None)
    if repository is None:
        logger.warning(
            "chapter draft binding repository unavailable novel_id=%s chapter_id=%s",
            novel_id,
            chapter.id,
        )
        return

    normalized = service._normalize_draft_binding(draft_binding)
    repository.upsert_binding(
        chapter_id=chapter.id,
        novel_id=novel_id,
        draft_type=normalized["draft_type"],
        draft_id=normalized["draft_id"],
        plan_version=normalized["plan_version"],
        state_lock_version=normalized["state_lock_version"],
        source_fusion_id=normalized.get("source_fusion_id"),
    )
    logger.info(
        "chapter save bound latest fusion novel_id=%s chapter_id=%s fusion_id=%s plan_version=%s state_lock_version=%s",
        novel_id,
        chapter.id,
        normalized.get("source_fusion_id"),
        normalized["plan_version"],
        normalized["state_lock_version"],
    )


def _build_update_response(chapter: ChapterDTO, aftermath: dict[str, Any]) -> UpdateChapterResponse:
    return UpdateChapterResponse(
        id=chapter.id,
        novel_id=chapter.novel_id,
        number=chapter.number,
        title=chapter.title,
        content=chapter.content,
        word_count=chapter.word_count,
        status=chapter.status,
        aftermath=ChapterAftermathStatusResponse(
            narrative_sync_ok=bool(aftermath.get("narrative_sync_ok", False)),
            voice_sync_ok=bool(aftermath.get("voice_sync_ok", True)),
            kg_sync_ok=bool(aftermath.get("kg_sync_ok", True)),
            local_sync_ok=bool(aftermath.get("local_sync_ok", False)),
            local_sync_errors=[str(item) for item in aftermath.get("local_sync_errors", []) if str(item).strip()],
            drift_alert=bool(aftermath.get("drift_alert", False)),
            similarity_score=aftermath.get("similarity_score"),
        ),
    )


@router.put("/{novel_id}/chapters/{chapter_number}", response_model=UpdateChapterResponse)
async def update_chapter(
    novel_id: str,
    request: UpdateChapterContentRequest,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service),
    pipeline: ChapterAftermathPipeline = Depends(get_chapter_aftermath_pipeline),
):
    """同步更新章节内容，并要求本地章后处理全部成功后才返回成功。"""
    existing = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
    original_content = existing.content if existing else ""
    draft_binding = _resolve_latest_fusion_draft_binding(service, pipeline, existing, request.draft_binding) if existing else None
    try:
        chapter = service.update_chapter_by_novel_and_number(
            novel_id,
            chapter_number,
            request.content,
            request.generation_metrics,
            None,
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    aftermath = await pipeline.run_after_chapter_saved(novel_id, chapter_number, request.content)
    if not aftermath.get("local_sync_ok", False):
        _rollback_chapter_content(service, novel_id, chapter_number, original_content)
        errors = [str(item) for item in aftermath.get("local_sync_errors", []) if str(item).strip()]
        raise HTTPException(
            status_code=500,
            detail={
                "message": "保存失败：章后本地同步未完成，正文已回滚",
                "aftermath": {
                    "narrative_sync_ok": bool(aftermath.get("narrative_sync_ok", False)),
                    "voice_sync_ok": bool(aftermath.get("voice_sync_ok", True)),
                    "kg_sync_ok": bool(aftermath.get("kg_sync_ok", True)),
                    "local_sync_ok": False,
                    "local_sync_errors": errors,
                },
            },
        )

    _persist_chapter_draft_binding(service, novel_id, chapter, draft_binding)
    return _build_update_response(chapter, aftermath)


@router.get(
    "/{novel_id}/chapters/{chapter_number}/generation-metrics",
    response_model=ChapterGenerationMetricsResponse
)
async def get_chapter_generation_metrics(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    metrics = service.get_chapter_generation_metrics(novel_id, chapter_number)
    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Generation metrics not found: {novel_id}/chapter-{chapter_number}")
    return ChapterGenerationMetricsResponse(**metrics.__dict__)


@router.get("/{novel_id}/chapters/{chapter_number}/review", response_model=ChapterReviewResponse)
async def get_chapter_review(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节审阅

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节审阅信息

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        review = service.get_chapter_review(novel_id, chapter_number)
        return ChapterReviewResponse(
            status=review.status,
            memo=review.memo,
            created_at=review.created_at.isoformat(),
            updated_at=review.updated_at.isoformat()
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{novel_id}/chapters/{chapter_number}/review", response_model=ChapterReviewResponse)
async def save_chapter_review(
    novel_id: str,
    request: SaveChapterReviewRequest,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service),
    validation_service: ValidationService = Depends(get_validation_service),
):
    """保存章节审阅

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        request: 审阅请求
        service: Chapter 服务

    Returns:
        保存后的审阅信息

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        logger.info(
            "chapter review save requested novel_id=%s chapter_number=%s status=%s",
            novel_id,
            chapter_number,
            request.status,
        )
        if request.status == "approved":
            chapter = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
            if chapter is None:
                raise HTTPException(status_code=404, detail=f"Chapter not found: {novel_id}/chapter-{chapter_number}")
            logger.info(
                "publish gate check requested chapter_id=%s novel_id=%s chapter_number=%s",
                chapter.id,
                novel_id,
                chapter_number,
            )
            publishable, report, blocking_issues = await validation_service.get_publish_gate_status(chapter.id)
            if not publishable:
                logger.warning(
                    "publish gate blocked chapter_id=%s report_id=%s blocking_issue_count=%s",
                    chapter.id,
                    report.report_id,
                    len(blocking_issues),
                )
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Publish blocked by unresolved blocking validation issues",
                        "report_id": report.report_id,
                        "blocking_issue_count": report.blocking_issue_count,
                        "issues": [
                            {
                                "issue_id": issue.issue_id,
                                "severity": issue.severity,
                                "title": issue.title,
                                "message": issue.message,
                            }
                            for issue in blocking_issues
                        ],
                    },
                )
            logger.info(
                "publish gate passed chapter_id=%s report_id=%s blocking_issue_count=%s",
                chapter.id,
                report.report_id,
                len(blocking_issues),
            )
        review = service.save_chapter_review(
            novel_id,
            chapter_number,
            request.status,
            request.memo
        )
        logger.info(
            "chapter review saved novel_id=%s chapter_number=%s status=%s",
            novel_id,
            chapter_number,
            review.status,
        )
        return ChapterReviewResponse(
            status=review.status,
            memo=review.memo,
            created_at=review.created_at.isoformat(),
            updated_at=review.updated_at.isoformat()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{novel_id}/chapters/{chapter_number}/review-ai")
async def ai_review_chapter(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """AI 审阅章节

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        AI 审阅结果

    Raises:
        HTTPException: 如果章节不存在或内容为空
    """
    try:
        # 获取章节
        chapter = service.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if chapter is None:
            raise HTTPException(status_code=404, detail=f"Chapter not found: {novel_id}/chapter-{chapter_number}")

        # 检查内容是否为空
        if not chapter.content or not chapter.content.strip():
            raise HTTPException(status_code=400, detail="Chapter content is empty")

        # TODO: 实现 AI 审阅逻辑
        # 这里需要集成 LLM 服务进行审阅
        return {
            "message": "AI review not yet implemented",
            "status": "pending"
        }
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{novel_id}/chapters/{chapter_number}/structure", response_model=ChapterStructureResponse)
async def get_chapter_structure(
    novel_id: str,
    chapter_number: int = Path(..., gt=0, description="章节编号"),
    service: ChapterService = Depends(get_chapter_service)
):
    """获取章节结构分析

    Args:
        novel_id: 小说 ID
        chapter_number: 章节号
        service: Chapter 服务

    Returns:
        章节结构分析

    Raises:
        HTTPException: 如果章节不存在
    """
    try:
        structure = service.get_chapter_structure(novel_id, chapter_number)
        return ChapterStructureResponse(
            word_count=structure.word_count,
            paragraph_count=structure.paragraph_count,
            dialogue_ratio=structure.dialogue_ratio,
            scene_count=structure.scene_count,
            pacing=structure.pacing
        )
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
