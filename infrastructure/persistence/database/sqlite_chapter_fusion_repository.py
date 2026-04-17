"""SQLite chapter fusion repository."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from application.core.dtos.chapter_fusion_dto import FusionDraftDTO, FusionJobDTO, FusionSuspenseBudgetDTO
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteChapterFusionRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def create_job(
        self,
        fusion_job_id: str,
        chapter_id: str,
        novel_id: str,
        plan_version: int,
        state_lock_version: int,
        beat_ids: List[str],
        target_words: int,
        suspense_budget: Dict[str, Any],
    ) -> FusionJobDTO:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO fusion_jobs (
                fusion_job_id,
                chapter_id,
                novel_id,
                plan_version,
                state_lock_version,
                beat_ids_json,
                target_words,
                suspense_budget_json,
                status,
                error_message,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', '', ?, ?)
            """,
            (
                fusion_job_id,
                chapter_id,
                novel_id,
                int(plan_version),
                int(state_lock_version),
                json.dumps(list(beat_ids), ensure_ascii=False),
                int(target_words),
                json.dumps(suspense_budget or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.db.get_connection().commit()
        return self.get_job(fusion_job_id)

    def update_job_status(self, fusion_job_id: str, status: str, error_message: str = "") -> None:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            UPDATE fusion_jobs
            SET status = ?, error_message = ?, updated_at = ?
            WHERE fusion_job_id = ?
            """,
            (status, error_message, now, fusion_job_id),
        )
        self.db.get_connection().commit()

    def save_draft(
        self,
        fusion_job_id: str,
        chapter_id: str,
        fusion_id: str,
        source_beat_ids: List[str],
        plan_version: int,
        state_lock_version: int,
        text: str,
        repeat_ratio: float,
        facts_confirmed: List[str],
        open_questions: List[str],
        end_state: Dict[str, Any],
        warnings: List[str],
        status: str,
    ) -> FusionDraftDTO:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO chapter_fusion_drafts (
                fusion_id,
                fusion_job_id,
                chapter_id,
                source_beat_ids_json,
                plan_version,
                state_lock_version,
                text,
                repeat_ratio,
                facts_confirmed_json,
                open_questions_json,
                end_state_json,
                warnings_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fusion_id) DO UPDATE SET
                fusion_job_id = excluded.fusion_job_id,
                chapter_id = excluded.chapter_id,
                source_beat_ids_json = excluded.source_beat_ids_json,
                plan_version = excluded.plan_version,
                state_lock_version = excluded.state_lock_version,
                text = excluded.text,
                repeat_ratio = excluded.repeat_ratio,
                facts_confirmed_json = excluded.facts_confirmed_json,
                open_questions_json = excluded.open_questions_json,
                end_state_json = excluded.end_state_json,
                warnings_json = excluded.warnings_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                fusion_id,
                fusion_job_id,
                chapter_id,
                json.dumps(list(source_beat_ids), ensure_ascii=False),
                int(plan_version),
                int(state_lock_version),
                text,
                float(repeat_ratio),
                json.dumps(facts_confirmed, ensure_ascii=False),
                json.dumps(open_questions, ensure_ascii=False),
                json.dumps(end_state, ensure_ascii=False),
                json.dumps(warnings, ensure_ascii=False),
                status,
                now,
                now,
            ),
        )
        self.db.execute(
            """
            UPDATE fusion_jobs
            SET status = ?, updated_at = ?
            WHERE fusion_job_id = ?
            """,
            (status, now, fusion_job_id),
        )
        self.db.get_connection().commit()
        return self.get_draft_by_job(fusion_job_id)

    def get_job(self, fusion_job_id: str) -> Optional[FusionJobDTO]:
        row = self.db.fetch_one(
            """
            SELECT * FROM fusion_jobs WHERE fusion_job_id = ?
            """,
            (fusion_job_id,),
        )
        if not row:
            return None
        draft = self.get_draft_by_job(fusion_job_id)
        return FusionJobDTO(
            fusion_job_id=row["fusion_job_id"],
            chapter_id=row["chapter_id"],
            plan_version=int(row["plan_version"] or 0),
            state_lock_version=int(row["state_lock_version"] or 0),
            beat_ids=json.loads(row.get("beat_ids_json") or "[]"),
            target_words=int(row.get("target_words") or 0),
            suspense_budget=FusionSuspenseBudgetDTO.from_dict(json.loads(row.get("suspense_budget_json") or "{}")),
            status=row.get("status") or "queued",
            error_message=row.get("error_message") or "",
            fusion_draft=draft,
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )

    def get_draft_by_job(self, fusion_job_id: str) -> Optional[FusionDraftDTO]:
        row = self.db.fetch_one(
            """
            SELECT * FROM chapter_fusion_drafts WHERE fusion_job_id = ?
            """,
            (fusion_job_id,),
        )
        if not row:
            return None
        return FusionDraftDTO(
            fusion_id=row["fusion_id"],
            chapter_id=row["chapter_id"],
            text=row.get("text") or "",
            estimated_repeat_ratio=float(row.get("repeat_ratio") or 0.0),
            facts_confirmed=json.loads(row.get("facts_confirmed_json") or "[]"),
            open_questions=json.loads(row.get("open_questions_json") or "[]"),
            end_state=json.loads(row.get("end_state_json") or "{}"),
            warnings=json.loads(row.get("warnings_json") or "[]"),
        )

    def add_log(self, fusion_job_id: str, chapter_id: str, step_name: str, step_status: str, message: str) -> None:
        self.db.execute(
            """
            INSERT INTO fusion_job_logs (
                fusion_job_id,
                chapter_id,
                step_name,
                step_status,
                message,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fusion_job_id,
                chapter_id,
                step_name,
                step_status,
                message,
                datetime.utcnow().isoformat(),
            ),
        )
        self.db.get_connection().commit()

    def list_logs(self, fusion_job_id: str) -> List[Dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT fusion_job_id, chapter_id, step_name, step_status, message, created_at
            FROM fusion_job_logs
            WHERE fusion_job_id = ?
            ORDER BY id ASC
            """,
            (fusion_job_id,),
        )

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

