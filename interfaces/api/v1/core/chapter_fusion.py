"""章节融合 API。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.core.services.chapter_fusion_service import ChapterFusionService
from interfaces.api.dependencies import get_chapter_fusion_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chapter-fusion"])


class SuspenseBudgetRequest(BaseModel):
    primary: int = Field(default=0, ge=0)
    secondary: int = Field(default=0, ge=0)


class CreateFusionJobRequest(BaseModel):
    plan_version: int = Field(..., gt=0)
    state_lock_version: int = Field(..., gt=0)
    beat_ids: List[str] = Field(default_factory=list)
    target_words: int = Field(..., gt=0)
    suspense_budget: SuspenseBudgetRequest = Field(default_factory=SuspenseBudgetRequest)


class FusionDraftResponse(BaseModel):
    fusion_id: str
    chapter_id: str
    text: str
    estimated_repeat_ratio: float
    facts_confirmed: List[str]
    open_questions: List[str]
    end_state: Dict[str, Any]
    warnings: List[str]


class FusionJobResponse(BaseModel):
    fusion_job_id: str
    chapter_id: str
    status: str
    error_message: str = ""
    fusion_draft: FusionDraftResponse | None = None
    preview: Dict[str, Any] | None = None


@router.post("/chapters/{chapter_id}/fusion-jobs", response_model=FusionJobResponse, status_code=201)
async def create_fusion_job(
    chapter_id: str,
    request: CreateFusionJobRequest,
    background_tasks: BackgroundTasks,
    service: ChapterFusionService = Depends(get_chapter_fusion_service),
):
    try:
        job = service.create_job(
            chapter_id=chapter_id,
            plan_version=request.plan_version,
            state_lock_version=request.state_lock_version,
            beat_ids=request.beat_ids,
            target_words=request.target_words,
            suspense_budget=request.suspense_budget.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    background_tasks.add_task(service.run_job, job.fusion_job_id)
    return FusionJobResponse(
        fusion_job_id=job.fusion_job_id,
        chapter_id=job.chapter_id,
        status=job.status,
        error_message=job.error_message,
        preview=job.preview,
    )


@router.get("/fusion-jobs/{fusion_job_id}", response_model=FusionJobResponse)
async def get_fusion_job(
    fusion_job_id: str = Path(..., description="融合任务 ID"),
    service: ChapterFusionService = Depends(get_chapter_fusion_service),
):
    job = service.get_job(fusion_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Fusion job not found: {fusion_job_id}")
    draft = job.fusion_draft
    return FusionJobResponse(
        fusion_job_id=job.fusion_job_id,
        chapter_id=job.chapter_id,
        status=job.status,
        error_message=job.error_message,
        fusion_draft=FusionDraftResponse(**draft.__dict__) if draft else None,
        preview=job.preview,
    )

