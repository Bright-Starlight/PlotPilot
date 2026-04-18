"""Chapter draft binding DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ChapterDraftBindingDTO:
    chapter_id: str
    novel_id: str
    draft_type: str
    draft_id: str
    plan_version: int
    state_lock_version: int
    source_fusion_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
