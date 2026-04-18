"""SQLite repository for chapter draft bindings."""
from __future__ import annotations

from datetime import datetime

from application.core.dtos.chapter_draft_binding_dto import ChapterDraftBindingDTO
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteChapterDraftBindingRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def upsert_binding(
        self,
        *,
        chapter_id: str,
        novel_id: str,
        draft_type: str,
        draft_id: str,
        plan_version: int,
        state_lock_version: int,
        source_fusion_id: str | None = None,
    ) -> ChapterDraftBindingDTO:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO chapter_draft_bindings (
                chapter_id,
                novel_id,
                draft_type,
                draft_id,
                plan_version,
                state_lock_version,
                source_fusion_id,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chapter_id, draft_type, draft_id) DO UPDATE SET
                novel_id = excluded.novel_id,
                plan_version = excluded.plan_version,
                state_lock_version = excluded.state_lock_version,
                source_fusion_id = excluded.source_fusion_id,
                updated_at = excluded.updated_at
            """,
            (
                chapter_id,
                novel_id,
                draft_type,
                draft_id,
                int(plan_version),
                int(state_lock_version),
                source_fusion_id,
                now,
                now,
            ),
        )
        self.db.get_connection().commit()
        binding = self.get_binding(chapter_id=chapter_id, draft_type=draft_type, draft_id=draft_id)
        if binding is None:
            raise ValueError("Chapter draft binding not found after upsert")
        return binding

    def get_binding(
        self,
        *,
        chapter_id: str,
        draft_type: str,
        draft_id: str,
    ) -> ChapterDraftBindingDTO | None:
        row = self.db.fetch_one(
            """
            SELECT *
            FROM chapter_draft_bindings
            WHERE chapter_id = ? AND draft_type = ? AND draft_id = ?
            """,
            (chapter_id, draft_type, draft_id),
        )
        if not row:
            return None
        return self._build_dto(row)

    def get_latest_binding(
        self,
        *,
        chapter_id: str,
        draft_type: str,
    ) -> ChapterDraftBindingDTO | None:
        row = self.db.fetch_one(
            """
            SELECT *
            FROM chapter_draft_bindings
            WHERE chapter_id = ? AND draft_type = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (chapter_id, draft_type),
        )
        if not row:
            return None
        return self._build_dto(row)

    @staticmethod
    def _build_dto(row: dict) -> ChapterDraftBindingDTO:
        return ChapterDraftBindingDTO(
            chapter_id=row["chapter_id"],
            novel_id=row["novel_id"],
            draft_type=row["draft_type"],
            draft_id=row["draft_id"],
            plan_version=int(row.get("plan_version") or 0),
            state_lock_version=int(row.get("state_lock_version") or 0),
            source_fusion_id=row.get("source_fusion_id"),
            created_at=SqliteChapterDraftBindingRepository._parse_dt(row.get("created_at")),
            updated_at=SqliteChapterDraftBindingRepository._parse_dt(row.get("updated_at")),
        )

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
