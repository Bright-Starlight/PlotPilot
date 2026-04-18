"""State lock DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


LOCK_GROUP_KEYS = (
    "time_lock",
    "location_lock",
    "character_lock",
    "item_lock",
    "numeric_lock",
    "event_lock",
    "ending_lock",
)


@dataclass
class StateLockSnapshotDTO:
    state_lock_id: str
    chapter_id: str
    novel_id: str
    version: int
    plan_version: int
    source: str
    change_reason: str = ""
    locks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    changed_fields: List[str] = field(default_factory=list)
    inference_notes: List[str] = field(default_factory=list)
    critical_change: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

