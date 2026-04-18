"""Validation DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class ValidationSpanDTO:
    paragraph_index: int
    start_offset: int
    end_offset: int
    excerpt: str


@dataclass
class ValidationIssueDTO:
    issue_id: str
    report_id: str
    chapter_id: str
    severity: str
    code: str
    title: str
    message: str
    spans: List[ValidationSpanDTO] = field(default_factory=list)
    blocking: bool = False
    suggest_patch: bool = False
    status: str = "unresolved"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationTokenUsageDTO:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "ValidationTokenUsageDTO":
        data = data or {}
        input_tokens = int(data.get("input_tokens") or 0)
        output_tokens = int(data.get("output_tokens") or 0)
        total_tokens = int(data.get("total_tokens") or (input_tokens + output_tokens))
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


@dataclass
class ValidationReportDTO:
    report_id: str
    chapter_id: str
    draft_type: str
    draft_id: str
    plan_version: int
    state_lock_version: int
    status: str
    passed: bool
    blocking_issue_count: int = 0
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    token_usage: ValidationTokenUsageDTO = field(default_factory=ValidationTokenUsageDTO)
    issues: List[ValidationIssueDTO] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ValidationRepairPatchDTO:
    issue_id: str
    patch_text: str
    source: str

