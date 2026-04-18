"""章节融合相关 DTO。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class FusionSuspenseBudgetDTO:
    primary: int = 0
    secondary: int = 0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "FusionSuspenseBudgetDTO":
        data = data or {}
        return cls(
            primary=int(data.get("primary") or 0),
            secondary=int(data.get("secondary") or 0),
        )


@dataclass
class FusionDraftDTO:
    fusion_id: str
    chapter_id: str
    plan_version: int
    state_lock_version: int
    text: str
    estimated_repeat_ratio: float
    status: str = "draft"
    facts_confirmed: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    end_state: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    state_lock_violations: List[Dict[str, Any]] = field(default_factory=list)
    latest_validation_report_id: str = ""


@dataclass
class FusionJobDTO:
    fusion_job_id: str
    chapter_id: str
    plan_version: int
    state_lock_version: int
    beat_ids: List[str]
    target_words: int
    suspense_budget: FusionSuspenseBudgetDTO
    status: str
    error_message: str = ""
    fusion_draft: Optional[FusionDraftDTO] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def preview(self) -> Dict[str, Any]:
        draft = self.fusion_draft
        return {
            "estimated_words": self._estimate_words(draft.text) if draft else 0,
            "estimated_repeat_ratio": draft.estimated_repeat_ratio if draft else 0.0,
            "expected_end_state": draft.end_state if draft else {},
            "expected_suspense_count": self.suspense_budget.primary + self.suspense_budget.secondary,
            "risk_warnings": draft.warnings if draft else [],
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
