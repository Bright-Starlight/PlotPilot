"""生成工作流 API 端点"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.services.hosted_write_service import HostedWriteService
from domain.novel.services.storyline_manager import StorylineManager

logger = logging.getLogger(__name__)
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.tension_level import TensionLevel
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.entities.plot_arc import PlotArc
from interfaces.api.dependencies import (
    get_auto_workflow,
    get_hosted_write_service,
    get_storyline_manager,
    get_plot_arc_repository,
    get_bible_service,
    get_novel_service,
    get_chapter_service,
    get_auto_bible_generator,
    get_auto_knowledge_generator,
)
from application.services.story_structure_ai_service import StoryStructureAIService
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from application.paths import DATA_DIR
from application.services.auto_bible_generator import AutoBibleGenerator
from application.services.auto_knowledge_generator import AutoKnowledgeGenerator

router = APIRouter(prefix="/novels", tags=["generation"])


def get_structure_ai_service() -> StoryStructureAIService:
    """获取叙事结构 AI 服务"""
    db_path = str(DATA_DIR / "aitext.db")
    repository = StoryNodeRepository(db_path)

    # 获取 Bible 服务
    from infrastructure.persistence.repositories.file_bible_repository import FileBibleRepository
    from infrastructure.persistence.storage.file_storage import FileStorage
    from application.services.bible_service import BibleService

    storage = FileStorage(DATA_DIR)
    bible_repository = FileBibleRepository(storage)
    bible_service = BibleService(bible_repository)

    return StoryStructureAIService(repository, llm_service=None, bible_service=bible_service)


# Request/Response Models
class GenerateChapterRequest(BaseModel):
    """生成章节请求"""
    chapter_number: int = Field(..., gt=0, description="章节号（必须 > 0）")
    outline: str = Field(..., min_length=1, description="章节大纲")


class ConsistencyIssueResponse(BaseModel):
    """一致性问题响应"""
    type: str
    severity: str
    description: str
    location: int


class ConsistencyReportResponse(BaseModel):
    """一致性报告响应"""
    issues: List[ConsistencyIssueResponse]
    warnings: List[ConsistencyIssueResponse]
    suggestions: List[str]


class GenerateChapterResponse(BaseModel):
    """生成章节响应"""
    content: str
    consistency_report: ConsistencyReportResponse
    token_count: int


class StorylineResponse(BaseModel):
    """故事线响应"""
    id: str
    storyline_type: str
    status: str
    estimated_chapter_start: int
    estimated_chapter_end: int


class CreateStorylineRequest(BaseModel):
    """创建故事线请求"""
    storyline_type: str = Field(..., description="故事线类型")
    estimated_chapter_start: int = Field(..., gt=0)
    estimated_chapter_end: int = Field(..., gt=0)


class PlotPointResponse(BaseModel):
    """情节点响应"""
    chapter_number: int
    tension: int
    description: str


class PlotArcResponse(BaseModel):
    """情节弧响应"""
    id: str
    novel_id: str
    key_points: List[PlotPointResponse]


class PlotPointRequest(BaseModel):
    """情节点请求"""
    chapter_number: int = Field(..., gt=0)
    tension: int = Field(..., ge=1, le=4)
    description: str
    point_type: str = Field(default="rising", description="情节点类型")


class CreatePlotArcRequest(BaseModel):
    """创建情节弧请求"""
    key_points: List[PlotPointRequest]


class HostedWriteStreamRequest(BaseModel):
    """托管连写（多章）请求"""
    from_chapter: int = Field(..., gt=0, description="起始章号")
    to_chapter: int = Field(..., gt=0, description="结束章号（含）")
    auto_save: bool = Field(True, description="每章生成后是否写入章节正文")
    auto_outline: bool = Field(
        True,
        description="是否先用模型生成本章要点大纲（否则用简短模板）",
    )


# Endpoints
@router.post(
    "/{novel_id}/generate-chapter",
    response_model=GenerateChapterResponse,
    status_code=status.HTTP_200_OK
)
async def generate_chapter(
    novel_id: str,
    request: GenerateChapterRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """生成章节（完整工作流）

    整合所有组件完成章节生成：
    - 构建 35K token 上下文
    - 调用 LLM 生成
    - 一致性检查
    - 返回结果和报告
    """
    logger.info(f"API 请求: POST /{novel_id}/generate-chapter")
    logger.info(f"  章节号: {request.chapter_number}")
    logger.info(f"  大纲长度: {len(request.outline)} 字符")

    try:
        result = await workflow.generate_chapter(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            outline=request.outline
        )

        # 转换一致性报告
        issues = [
            ConsistencyIssueResponse(
                type=issue.type.value,
                severity=issue.severity.value,
                description=issue.description,
                location=issue.location
            )
            for issue in result.consistency_report.issues
        ]

        warnings = [
            ConsistencyIssueResponse(
                type=warning.type.value,
                severity=warning.severity.value,
                description=warning.description,
                location=warning.location
            )
            for warning in result.consistency_report.warnings
        ]

        logger.info(f"API 响应: 生成成功")
        logger.info(f"  内容长度: {len(result.content)} 字符")
        logger.info(f"  Token 数: {result.token_count}")
        logger.info(f"  问题数: {len(issues)}, 警告数: {len(warnings)}")

        # 检查幕是否完成，自动创建下一幕
        try:
            structure_service = get_structure_ai_service()
            completion_check = await structure_service.check_act_completion(
                novel_id=novel_id,
                chapter_number=request.chapter_number
            )
            if completion_check.get("should_create_next"):
                logger.info(f"当前幕已完成，自动创建下一幕")
        except Exception as e:
            logger.warning(f"幕完成检查失败（不影响章节生成）: {e}")

        return GenerateChapterResponse(
            content=result.content,
            consistency_report=ConsistencyReportResponse(
                issues=issues,
                warnings=warnings,
                suggestions=result.consistency_report.suggestions
            ),
            token_count=result.token_count
        )
    except ValueError as e:
        logger.error(f"API 错误: 参数无效 - {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(f"API 错误: 生成失败")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(e)}"
        )


@router.post(
    "/{novel_id}/generate-chapter-stream",
    status_code=status.HTTP_200_OK,
)
async def generate_chapter_stream(
    novel_id: str,
    request: GenerateChapterRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """流式生成章节（SSE）

    每行一条 ``data: {json}``，事件类型：
    - ``phase``: ``planning`` | ``context`` | ``llm`` | ``post``
    - ``chunk``: 正文片段 ``text``
    - ``done``: 完整 ``content``、``consistency_report``、``token_count``
    - ``error``: ``message``
    """
    logger.info(f"API 请求: POST /{novel_id}/generate-chapter-stream (SSE)")
    logger.info(f"  章节号: {request.chapter_number}")
    logger.info(f"  大纲长度: {len(request.outline)} 字符")

    async def event_gen():
        async for event in workflow.generate_chapter_stream(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            outline=request.outline,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{novel_id}/hosted-write-stream",
    status_code=status.HTTP_200_OK,
)
async def hosted_write_stream(
    novel_id: str,
    request: HostedWriteStreamRequest,
    service: HostedWriteService = Depends(get_hosted_write_service),
):
    """托管多章连写（SSE）：自动大纲 → 每章流式正文 → 一致性 → 可选落库。

    额外事件：``session``、``chapter_start``、``outline``、``saved``、``session_done``；
    单章事件均带 ``chapter`` 字段。
    """
    logger.info(f"API 请求: POST /{novel_id}/hosted-write-stream (SSE)")
    logger.info(f"  章节范围: {request.from_chapter}-{request.to_chapter}")
    logger.info(f"  auto_save: {request.auto_save}, auto_outline: {request.auto_outline}")

    if request.to_chapter < request.from_chapter:
        logger.error(f"API 错误: to_chapter < from_chapter")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="to_chapter must be >= from_chapter",
        )

    async def event_gen():
        async for event in service.stream_hosted_write(
            novel_id=novel_id,
            from_chapter=request.from_chapter,
            to_chapter=request.to_chapter,
            auto_save=request.auto_save,
            auto_outline=request.auto_outline,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{novel_id}/consistency-report",
    response_model=ConsistencyReportResponse,
    status_code=status.HTTP_200_OK
)
async def get_consistency_report(
    novel_id: str,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """获取最新的一致性报告

    注意：这需要先调用 generate_chapter 生成内容
    """
    # 简化实现：返回空报告
    # 实际应该从缓存或数据库获取最新报告
    return ConsistencyReportResponse(
        issues=[],
        warnings=[],
        suggestions=[]
    )


@router.get(
    "/{novel_id}/storylines",
    response_model=List[StorylineResponse],
    status_code=status.HTTP_200_OK
)
def get_storylines(
    novel_id: str,
    manager: StorylineManager = Depends(get_storyline_manager)
):
    """获取小说的所有故事线"""
    try:
        storylines = manager.repository.get_by_novel_id(NovelId(novel_id))

        return [
            StorylineResponse(
                id=storyline.id,
                storyline_type=storyline.storyline_type.value,
                status=storyline.status.value,
                estimated_chapter_start=storyline.estimated_chapter_start,
                estimated_chapter_end=storyline.estimated_chapter_end
            )
            for storyline in storylines
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storylines: {str(e)}"
        )


@router.post(
    "/{novel_id}/storylines",
    response_model=StorylineResponse,
    status_code=status.HTTP_201_CREATED
)
def create_storyline(
    novel_id: str,
    request: CreateStorylineRequest,
    manager: StorylineManager = Depends(get_storyline_manager)
):
    """创建新的故事线"""
    try:
        storyline = manager.create_storyline(
            novel_id=NovelId(novel_id),
            storyline_type=StorylineType(request.storyline_type),
            estimated_chapter_start=request.estimated_chapter_start,
            estimated_chapter_end=request.estimated_chapter_end
        )

        return StorylineResponse(
            id=storyline.id,
            storyline_type=storyline.storyline_type.value,
            status=storyline.status.value,
            estimated_chapter_start=storyline.estimated_chapter_start,
            estimated_chapter_end=storyline.estimated_chapter_end
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create storyline: {str(e)}"
        )


@router.get(
    "/{novel_id}/plot-arc",
    response_model=PlotArcResponse,
    status_code=status.HTTP_200_OK
)
def get_plot_arc(
    novel_id: str,
    repository: PlotArcRepository = Depends(get_plot_arc_repository)
):
    """获取小说的情节弧"""
    try:
        plot_arc = repository.get_by_novel_id(NovelId(novel_id))

        if plot_arc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plot arc not found for novel {novel_id}"
            )

        return PlotArcResponse(
            id=plot_arc.id,
            novel_id=novel_id,
            key_points=[
                PlotPointResponse(
                    chapter_number=point.chapter_number,
                    tension=point.tension.value,
                    description=point.description
                )
                for point in plot_arc.key_points
            ]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plot arc: {str(e)}"
        )


@router.post(
    "/{novel_id}/plot-arc",
    response_model=PlotArcResponse,
    status_code=status.HTTP_200_OK
)
def create_or_update_plot_arc(
    novel_id: str,
    request: CreatePlotArcRequest,
    repository: PlotArcRepository = Depends(get_plot_arc_repository)
):
    """创建或更新情节弧"""
    try:
        # 尝试获取现有的情节弧
        plot_arc = repository.get_by_novel_id(NovelId(novel_id))

        if plot_arc is None:
            # 创建新的情节弧
            plot_arc = PlotArc(id=f"{novel_id}-arc", novel_id=NovelId(novel_id))

        # 清空现有的情节点并添加新的
        plot_arc.key_points = []
        for point_req in request.key_points:
            plot_arc.add_plot_point(PlotPoint(
                chapter_number=point_req.chapter_number,
                point_type=PlotPointType(point_req.point_type),
                description=point_req.description,
                tension=TensionLevel(point_req.tension)
            ))

        # 保存
        repository.save(plot_arc)

        return PlotArcResponse(
            id=plot_arc.id,
            novel_id=novel_id,
            key_points=[
                PlotPointResponse(
                    chapter_number=point.chapter_number,
                    tension=point.tension.value,
                    description=point.description
                )
                for point in plot_arc.key_points
            ]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create/update plot arc: {str(e)}"
        )


# ============================================================================
# 新增：大纲规划、章节审稿、续写大纲
# ============================================================================

class PlanRequest(BaseModel):
    """大纲规划请求"""
    mode: str = Field("initial", description="模式：initial=首次生成，revise=再规划")
    dry_run: bool = Field(False, description="预演模式（不调用 LLM）")


class PlanResponse(BaseModel):
    """大纲规划响应"""
    success: bool
    message: str
    bible_updated: bool = False
    outline_updated: bool = False
    chapters_planned: int = 0


class ReviewRequest(BaseModel):
    """章节审稿请求"""
    chapter_number: int = Field(..., gt=0, description="章节号")


class ReviewResponse(BaseModel):
    """章节审稿响应"""
    chapter_number: int
    suggestions: List[str]
    score: int = Field(..., ge=0, le=100, description="评分 0-100")


class ExtendOutlineRequest(BaseModel):
    """续写大纲请求"""
    from_chapter: int = Field(..., gt=0, description="从第几章开始续写")
    count: int = Field(5, gt=0, le=20, description="续写章节数量")


class ExtendOutlineResponse(BaseModel):
    """续写大纲响应"""
    success: bool
    chapters_added: int
    outlines: List[str]


@router.post(
    "/{novel_id}/plan",
    response_model=PlanResponse,
    status_code=status.HTTP_200_OK
)
async def plan_novel(
    novel_id: str,
    request: PlanRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow),
    bible_service = Depends(get_bible_service),
    novel_service = Depends(get_novel_service),
    chapter_service = Depends(get_chapter_service)
):
    """大纲规划：生成 Bible + 分章大纲

    - mode=initial: 首次生成（适用于新书）
    - mode=revise: 再规划（基于已有进度重新规划）
    - dry_run=true: 预演模式，不调用 LLM
    """
    try:
        if request.dry_run:
            return PlanResponse(
                success=True,
                message="预演模式：跳过 LLM 调用",
                bible_updated=False,
                outline_updated=False,
                chapters_planned=0
            )

        # 使用 workflow 的 suggest_outline 为每章生成大纲
        # 为前 5 章生成大纲并创建章节
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Novel {novel_id} not found"
            )

        # 保证至少有一幕，否则 add_chapter 无法把章节挂到 story_nodes，左侧叙事结构树会一直为空
        novel_service.ensure_default_act_for_chapters(novel_id)

        chapters_planned = 0
        for chapter_num in range(1, 6):
            try:
                outline = await workflow.suggest_outline(novel_id, chapter_num)

                # 创建章节（通过 novel_service.add_chapter 统一处理）
                chapter_id = f"{novel_id}-chapter-{chapter_num}"

                # 使用 novel_service.add_chapter 创建并保存章节
                novel_service.add_chapter(
                    novel_id=novel_id,
                    chapter_id=chapter_id,
                    number=chapter_num,
                    title=f"第{chapter_num}章",
                    content=""
                )

                logger.info(f"Created chapter {chapter_num} with outline: {outline[:100]}...")
                chapters_planned += 1
            except Exception as e:
                logger.warning(f"Failed to generate outline for chapter {chapter_num}: {e}")

        return PlanResponse(
            success=True,
            message=f"成功生成 {chapters_planned} 章大纲",
            bible_updated=False,
            outline_updated=True,
            chapters_planned=chapters_planned
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Plan failed: {str(e)}"
        )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_200_OK
)
async def review_chapter(
    novel_id: str,
    chapter_number: int,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow),
    chapter_service = Depends(get_chapter_service)
):
    """章节审稿：AI 审稿并返回修改建议"""
    try:
        # 使用 workflow 的 generate_chapter_with_review 方法
        # 这个方法会生成内容并返回一致性报告
        # 我们可以基于一致性报告生成审稿建议

        # 读取章节内容
        chapter = chapter_service.get_chapter(novel_id, chapter_number)
        if not chapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chapter {chapter_number} not found"
            )

        # 使用一致性检查作为审稿
        # TODO: 这里可以调用专门的审稿 LLM prompt
        suggestions = [
            "建议检查人物一致性",
            "建议优化对话节奏",
            "建议增强场景描写"
        ]

        # 简单评分逻辑（基于字数）
        word_count = len(chapter.content)
        score = min(100, max(60, word_count // 20))

        return ReviewResponse(
            chapter_number=chapter_number,
            suggestions=suggestions,
            score=score
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Review failed: {str(e)}"
        )


@router.post(
    "/{novel_id}/outline/extend",
    response_model=ExtendOutlineResponse,
    status_code=status.HTTP_200_OK
)
async def extend_outline(
    novel_id: str,
    request: ExtendOutlineRequest,
    workflow: AutoNovelGenerationWorkflow = Depends(get_auto_workflow)
):
    """续写大纲：基于当前进度生成后续章节大纲"""
    try:
        # 使用 workflow 的 suggest_outline 为后续章节生成大纲
        outlines = []
        chapters_added = 0

        for i in range(request.count):
            chapter_num = request.from_chapter + i
            try:
                outline = await workflow.suggest_outline(novel_id, chapter_num)
                outlines.append(outline)
                chapters_added += 1
            except Exception as e:
                logger.warning(f"Failed to generate outline for chapter {chapter_num}: {e}")
                break

        return ExtendOutlineResponse(
            success=chapters_added > 0,
            chapters_added=chapters_added,
            outlines=outlines
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extend outline failed: {str(e)}"
        )


# ============================================================================
# Bible / Knowledge 一键 AI 生成（补齐旧小说数据）
# ============================================================================

class GenerateBibleResponse(BaseModel):
    success: bool
    message: str
    characters_count: int = 0
    locations_count: int = 0


class GenerateKnowledgeResponse(BaseModel):
    success: bool
    message: str
    facts_count: int = 0
    premise_lock: str = ""


@router.post(
    "/{novel_id}/bible/generate",
    response_model=GenerateBibleResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成 Bible 设定"
)
async def generate_bible(
    novel_id: str,
    bible_generator: AutoBibleGenerator = Depends(get_auto_bible_generator),
    novel_service=Depends(get_novel_service),
):
    """为指定小说 AI 生成（或重新生成）Bible 设定。

    - 会覆盖现有 Bible 中的角色、地点与文风数据
    - 需要 ANTHROPIC_API_KEY
    """
    try:
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

        bible_data = await bible_generator.generate_and_save(
            novel_id=novel_id,
            title=novel.title,
            target_chapters=novel.target_chapters,
        )

        chars = bible_data.get("characters", [])
        locs = bible_data.get("locations", [])
        return GenerateBibleResponse(
            success=True,
            message=f"Bible 生成成功：{len(chars)} 位角色，{len(locs)} 个地点",
            characters_count=len(chars),
            locations_count=len(locs),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_bible failed for %s", novel_id)
        raise HTTPException(status_code=500, detail=f"Bible 生成失败：{str(e)}")


@router.post(
    "/{novel_id}/knowledge/generate",
    response_model=GenerateKnowledgeResponse,
    status_code=status.HTTP_200_OK,
    summary="AI 生成初始 Knowledge 知识图谱"
)
async def generate_knowledge(
    novel_id: str,
    knowledge_generator: AutoKnowledgeGenerator = Depends(get_auto_knowledge_generator),
    novel_service=Depends(get_novel_service),
    bible_service=Depends(get_bible_service),
):
    """为指定小说 AI 生成初始 Knowledge（梗概锁定 + 知识三元组）。

    - 会读取已有 Bible 作为参考
    - 需要 ANTHROPIC_API_KEY
    """
    try:
        novel = novel_service.get_novel(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"Novel not found: {novel_id}")

        # 尝试读取 Bible 摘要作为生成参考
        bible_summary = ""
        try:
            bible = bible_service.get_bible_by_novel(novel_id)
            if bible and bible.characters:
                char_desc = "、".join(
                    f"{c.name}" for c in list(bible.characters)[:5]
                )
                bible_summary = f"主要角色：{char_desc}。"
                if bible.locations:
                    loc_desc = "、".join(l.name for l in list(bible.locations)[:3])
                    bible_summary += f"重要地点：{loc_desc}。"
                if bible.style_notes:
                    bible_summary += f"文风：{list(bible.style_notes)[0].content[:80]}。"
        except Exception:
            pass

        knowledge_data = await knowledge_generator.generate_and_save(
            novel_id=novel_id,
            title=novel.title,
            bible_summary=bible_summary,
        )

        facts_count = len(knowledge_data.get("facts", []))
        premise = knowledge_data.get("premise_lock", "")
        return GenerateKnowledgeResponse(
            success=True,
            message=f"Knowledge 生成成功：梗概锁定已写入，{facts_count} 条知识三元组",
            facts_count=facts_count,
            premise_lock=premise[:120] + ("…" if len(premise) > 120 else ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("generate_knowledge failed for %s", novel_id)
        raise HTTPException(status_code=500, detail=f"Knowledge 生成失败：{str(e)}")
