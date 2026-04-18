"""SQLite state lock repository."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from application.core.dtos.state_lock_dto import LOCK_GROUP_KEYS, StateLockSnapshotDTO
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteStateLockRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat()

    @staticmethod
    def _json(value: Any, fallback: Any) -> str:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)

    @staticmethod
    def _loads(value: Any, fallback: Any) -> Any:
        if value in (None, ""):
            return fallback
        try:
            return json.loads(value)
        except Exception:
            return fallback

    def get_current_by_chapter(self, chapter_id: str) -> Optional[StateLockSnapshotDTO]:
        row = self.db.fetch_one("SELECT * FROM state_locks WHERE chapter_id = ?", (chapter_id,))
        if not row:
            return None
        version = int(row.get("current_version") or 0)
        version_row = self.db.fetch_one(
            "SELECT * FROM state_lock_versions WHERE state_lock_id = ? AND version = ?",
            (row["state_lock_id"], version),
        )
        return self._row_to_snapshot(version_row or row, version_override=version)

    def get_version(self, state_lock_id: str, version: int) -> Optional[StateLockSnapshotDTO]:
        row = self.db.fetch_one(
            "SELECT * FROM state_lock_versions WHERE state_lock_id = ? AND version = ?",
            (state_lock_id, int(version)),
        )
        return self._row_to_snapshot(row) if row else None

    def get_version_by_chapter(self, chapter_id: str, version: int) -> Optional[StateLockSnapshotDTO]:
        row = self.db.fetch_one(
            "SELECT * FROM state_lock_versions WHERE chapter_id = ? AND version = ?",
            (chapter_id, int(version)),
        )
        return self._row_to_snapshot(row) if row else None

    def has_version(self, chapter_id: str, version: int) -> bool:
        row = self.db.fetch_one(
            "SELECT 1 AS present FROM state_lock_versions WHERE chapter_id = ? AND version = ?",
            (chapter_id, int(version)),
        )
        return row is not None

    def save_snapshot(
        self,
        *,
        chapter_id: str,
        novel_id: str,
        plan_version: int,
        locks: Dict[str, Dict[str, Any]],
        source: str,
        change_reason: str,
        changed_fields: List[str],
        inference_notes: List[str],
        critical_change: Dict[str, Any],
    ) -> StateLockSnapshotDTO:
        now = self._now()
        existing = self.db.fetch_one("SELECT * FROM state_locks WHERE chapter_id = ?", (chapter_id,))
        state_lock_id = existing["state_lock_id"] if existing else f"sl_{uuid.uuid4().hex[:12]}"
        next_version = int(existing.get("latest_version") or 0) + 1 if existing else 1
        version_id = f"slv_{uuid.uuid4().hex[:12]}"

        lock_params = [
            state_lock_id,
            chapter_id,
            novel_id,
            next_version,
            next_version,
            int(plan_version),
        ]
        for key in LOCK_GROUP_KEYS:
            lock_params.append(self._json(locks.get(key, {"entries": []}), {"entries": []}))
        lock_params.extend([change_reason, source, now, now])
        self.db.execute(
            f"""
            INSERT INTO state_locks (
                state_lock_id, chapter_id, novel_id, current_version, latest_version, plan_version,
                {", ".join(f"{k}_json" for k in LOCK_GROUP_KEYS)},
                last_change_reason, last_source, created_at, updated_at
            ) VALUES ({", ".join(["?"] * (6 + len(LOCK_GROUP_KEYS) + 4))})
            ON CONFLICT(chapter_id) DO UPDATE SET
                current_version = excluded.current_version,
                latest_version = excluded.latest_version,
                plan_version = excluded.plan_version,
                {", ".join(f"{k}_json = excluded.{k}_json" for k in LOCK_GROUP_KEYS)},
                last_change_reason = excluded.last_change_reason,
                last_source = excluded.last_source,
                updated_at = excluded.updated_at
            """,
            tuple(lock_params),
        )
        version_params = [
            version_id,
            state_lock_id,
            chapter_id,
            novel_id,
            next_version,
            int(plan_version),
            source,
            change_reason,
            self._json(changed_fields, []),
            self._json(inference_notes, []),
            self._json(critical_change, {}),
        ]
        for key in LOCK_GROUP_KEYS:
            version_params.append(self._json(locks.get(key, {"entries": []}), {"entries": []}))
        version_params.append(now)
        self.db.execute(
            f"""
            INSERT INTO state_lock_versions (
                state_lock_version_id, state_lock_id, chapter_id, novel_id, version,
                plan_version, source, change_reason, changed_fields_json, inference_notes_json,
                critical_change_json, {", ".join(f"{k}_json" for k in LOCK_GROUP_KEYS)}, created_at
            ) VALUES ({", ".join(["?"] * (11 + len(LOCK_GROUP_KEYS) + 1))})
            """,
            tuple(version_params),
        )
        self.db.get_connection().commit()
        return self.get_version(state_lock_id, next_version)

    def _row_to_snapshot(
        self,
        row: Dict[str, Any],
        *,
        version_override: int | None = None,
    ) -> StateLockSnapshotDTO:
        locks = {
            key: self._loads(row.get(f"{key}_json"), {"entries": []})
            for key in LOCK_GROUP_KEYS
        }
        created_at_raw = row.get("created_at")
        created_at = None
        if created_at_raw:
            try:
                created_at = datetime.fromisoformat(str(created_at_raw))
            except ValueError:
                created_at = None
        return StateLockSnapshotDTO(
            state_lock_id=row["state_lock_id"],
            chapter_id=row["chapter_id"],
            novel_id=row["novel_id"],
            version=int(version_override if version_override is not None else row.get("version") or 0),
            plan_version=int(row.get("plan_version") or 1),
            source=row.get("source") or row.get("last_source") or "generated",
            change_reason=row.get("change_reason") or row.get("last_change_reason") or "",
            locks=locks,
            changed_fields=self._loads(row.get("changed_fields_json"), []),
            inference_notes=self._loads(row.get("inference_notes_json"), []),
            critical_change=self._loads(row.get("critical_change_json"), {}),
            created_at=created_at,
        )
