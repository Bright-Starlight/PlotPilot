"""Validation report APIs."""
from __future__ import annotations

from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from application.core.services.validation_service import ValidationService
from interfaces.api.dependencies import get_validation_service

router = APIRouter(tags=["validation-reports"])


class ValidationSpanResponse(BaseModel):
    paragraph_index: int
    start_offset: int
    end_offset: int
    excerpt: str


class ValidationIssueResponse(BaseModel):
    issue_id: str
    report_id: str
    chapter_id: str
    severity: str
    code: str
    title: str
    message: str
    spans: List[ValidationSpanResponse] = Field(default_factory=list)
    blocking: bool
    suggest_patch: bool
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationTokenUsageResponse(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ValidationReportSummaryResponse(BaseModel):
    report_id: str
    chapter_id: str
    draft_type: str
    draft_id: str
    plan_version: int
    state_lock_version: int
    status: str
    passed: bool
    blocking_issue_count: int
    p0_count: int
    p1_count: int
    p2_count: int
    token_usage: ValidationTokenUsageResponse


class ValidationReportDetailResponse(ValidationReportSummaryResponse):
    issues_by_severity: Dict[str, List[ValidationIssueResponse]] = Field(default_factory=dict)


class StartValidationRequest(BaseModel):
    draft_type: Literal["fusion", "merged"]
    draft_id: str = Field(..., min_length=1)
    plan_version: int | None = Field(default=None, gt=0)
    state_lock_version: int | None = Field(default=None, gt=0)


class UpdateValidationIssueRequest(BaseModel):
    status: Literal["unresolved", "resolved", "ignored"]


class ValidationRepairPatchResponse(BaseModel):
    issue_id: str
    patch_text: str
    source: str


class PublishGateResponse(ValidationReportDetailResponse):
    publishable: bool
    blocking_issues: List[ValidationIssueResponse] = Field(default_factory=list)


class ManualPublishResponse(BaseModel):
    chapter_id: str
    fusion_id: str
    plan_version: int
    state_lock_version: int
    text_length: int
    published: bool


def _summary_response(report) -> ValidationReportSummaryResponse:
    return ValidationReportSummaryResponse(
        report_id=report.report_id,
        chapter_id=report.chapter_id,
        draft_type=report.draft_type,
        draft_id=report.draft_id,
        plan_version=report.plan_version,
        state_lock_version=report.state_lock_version,
        status=report.status,
        passed=report.passed,
        blocking_issue_count=report.blocking_issue_count,
        p0_count=report.p0_count,
        p1_count=report.p1_count,
        p2_count=report.p2_count,
        token_usage=ValidationTokenUsageResponse(**report.token_usage.__dict__),
    )


def _detail_response(report) -> ValidationReportDetailResponse:
    grouped = {"P0": [], "P1": [], "P2": []}
    for issue in report.issues:
        grouped.setdefault(issue.severity, []).append(
            ValidationIssueResponse(
                issue_id=issue.issue_id,
                report_id=issue.report_id,
                chapter_id=issue.chapter_id,
                severity=issue.severity,
                code=issue.code,
                title=issue.title,
                message=issue.message,
                spans=[ValidationSpanResponse(**span.__dict__) for span in issue.spans],
                blocking=issue.blocking,
                suggest_patch=issue.suggest_patch,
                status=issue.status,
                metadata=dict(issue.metadata or {}),
            )
        )
    return ValidationReportDetailResponse(
        **_summary_response(report).model_dump(),
        issues_by_severity=grouped,
    )


@router.post("/chapters/{chapter_id}/validate", response_model=ValidationReportSummaryResponse, status_code=201)
async def start_validation(
    chapter_id: str,
    request: StartValidationRequest,
    service: ValidationService = Depends(get_validation_service),
):
    try:
        report = await service.start_validation(
            chapter_id,
            draft_type=request.draft_type,
            draft_id=request.draft_id,
            plan_version=request.plan_version,
            state_lock_version=request.state_lock_version,
        )
        return _summary_response(report)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/validation-reports/{report_id}", response_model=ValidationReportDetailResponse)
async def get_validation_report(
    report_id: str,
    service: ValidationService = Depends(get_validation_service),
):
    try:
        return _detail_response(service.get_report(report_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/chapters/{chapter_id}/validation-reports/latest", response_model=ValidationReportDetailResponse)
async def get_latest_validation_report(
    chapter_id: str,
    draft_type: Literal["fusion", "merged"] = Query(default="fusion"),
    draft_id: str | None = Query(default=None),
    service: ValidationService = Depends(get_validation_service),
):
    try:
        return _detail_response(service.get_latest_report(chapter_id, draft_type=draft_type, draft_id=draft_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/validation-issues", response_model=List[ValidationIssueResponse])
async def list_validation_issues(
    novel_id: str | None = Query(default=None),
    chapter_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: ValidationService = Depends(get_validation_service),
):
    try:
        issues = service.list_issues(novel_id=novel_id, chapter_id=chapter_id, severity=severity, status=status)
        return [
            ValidationIssueResponse(
                issue_id=issue.issue_id,
                report_id=issue.report_id,
                chapter_id=issue.chapter_id,
                severity=issue.severity,
                code=issue.code,
                title=issue.title,
                message=issue.message,
                spans=[ValidationSpanResponse(**span.__dict__) for span in issue.spans],
                blocking=issue.blocking,
                suggest_patch=issue.suggest_patch,
                status=issue.status,
                metadata=dict(issue.metadata or {}),
            )
            for issue in issues
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/validation-issues/{issue_id}", response_model=ValidationIssueResponse)
async def update_validation_issue(
    issue_id: str,
    request: UpdateValidationIssueRequest,
    service: ValidationService = Depends(get_validation_service),
):
    try:
        issue = service.update_issue_status(issue_id, request.status)
        return ValidationIssueResponse(
            issue_id=issue.issue_id,
            report_id=issue.report_id,
            chapter_id=issue.chapter_id,
            severity=issue.severity,
            code=issue.code,
            title=issue.title,
            message=issue.message,
            spans=[ValidationSpanResponse(**span.__dict__) for span in issue.spans],
            blocking=issue.blocking,
            suggest_patch=issue.suggest_patch,
            status=issue.status,
            metadata=dict(issue.metadata or {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/validation-issues/{issue_id}/repair-patch", response_model=ValidationRepairPatchResponse)
async def build_validation_repair_patch(
    issue_id: str,
    service: ValidationService = Depends(get_validation_service),
):
    try:
        patch = await service.build_repair_patch(issue_id)
        return ValidationRepairPatchResponse(
            issue_id=patch.issue_id,
            patch_text=patch.patch_text,
            source=patch.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chapters/{chapter_id}/publish-check", response_model=PublishGateResponse)
async def check_publish_gate(
    chapter_id: str,
    service: ValidationService = Depends(get_validation_service),
):
    try:
        publishable, report, blocking_issues = await service.get_publish_gate_status(chapter_id)
        return PublishGateResponse(
            publishable=publishable,
            blocking_issues=[
                ValidationIssueResponse(
                    issue_id=issue.issue_id,
                    report_id=issue.report_id,
                    chapter_id=issue.chapter_id,
                    severity=issue.severity,
                    code=issue.code,
                    title=issue.title,
                    message=issue.message,
                    spans=[ValidationSpanResponse(**span.__dict__) for span in issue.spans],
                    blocking=issue.blocking,
                    suggest_patch=issue.suggest_patch,
                    status=issue.status,
                    metadata=dict(issue.metadata or {}),
                )
                for issue in blocking_issues
            ],
            **_detail_response(report).model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chapters/{chapter_id}/manual-publish", response_model=ManualPublishResponse)
async def manual_publish_fusion_draft(
    chapter_id: str,
    service: ValidationService = Depends(get_validation_service),
):
    """手动发布融合草稿到章节正文。

    用于 Validation 阶段 LLM 误判时，人工审阅后手动触发发布。
    将最新的融合草稿内容写入章节正文，与自动发布流程相同。

    Args:
        chapter_id: 章节 ID

    Returns:
        ManualPublishResponse: 包含发布结果的响应

    Raises:
        HTTPException: 400 - 章节不存在或没有融合草稿
    """
    try:
        result = service.manual_publish_fusion_draft(chapter_id)
        return ManualPublishResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
