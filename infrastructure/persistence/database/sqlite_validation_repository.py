"""SQLite validation report repository."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from application.core.dtos.validation_dto import (
    ValidationIssueDTO,
    ValidationReportDTO,
    ValidationSpanDTO,
    ValidationTokenUsageDTO,
)
from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteValidationRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def create_report(
        self,
        *,
        report_id: str,
        chapter_id: str,
        novel_id: str,
        draft_type: str,
        draft_id: str,
        plan_version: int,
        state_lock_version: int,
    ) -> ValidationReportDTO:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO validation_reports (
                report_id,
                chapter_id,
                novel_id,
                draft_type,
                draft_id,
                plan_version,
                state_lock_version,
                status,
                passed,
                blocking_issue_count,
                p0_count,
                p1_count,
                p2_count,
                token_usage_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', 0, 0, 0, 0, 0, '{}', ?, ?)
            """,
            (
                report_id,
                chapter_id,
                novel_id,
                draft_type,
                draft_id,
                int(plan_version),
                int(state_lock_version),
                now,
                now,
            ),
        )
        self.db.get_connection().commit()
        return self.get_report(report_id)

    def save_report_result(
        self,
        *,
        report_id: str,
        status: str,
        passed: bool,
        issues: List[ValidationIssueDTO],
        token_usage: ValidationTokenUsageDTO,
    ) -> ValidationReportDTO:
        report = self.get_report(report_id)
        if report is None:
            raise ValueError("Validation report not found")

        now = datetime.utcnow().isoformat()
        grouped = {"P0": 0, "P1": 0, "P2": 0}
        blocking_issue_count = 0
        for issue in issues:
            if issue.severity in grouped:
                grouped[issue.severity] += 1
            if issue.blocking and issue.status != "resolved":
                blocking_issue_count += 1

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM validation_issues WHERE report_id = ?", (report_id,))
            for issue in issues:
                conn.execute(
                    """
                    INSERT INTO validation_issues (
                        issue_id,
                        report_id,
                        chapter_id,
                        severity,
                        code,
                        title,
                        message,
                        spans_json,
                        blocking,
                        suggest_patch,
                        handling_status,
                        metadata_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue.issue_id,
                        report_id,
                        report.chapter_id,
                        issue.severity,
                        issue.code,
                        issue.title,
                        issue.message,
                        json.dumps(
                            [
                                {
                                    "paragraph_index": span.paragraph_index,
                                    "start_offset": span.start_offset,
                                    "end_offset": span.end_offset,
                                    "excerpt": span.excerpt,
                                }
                                for span in issue.spans
                            ],
                            ensure_ascii=False,
                        ),
                        1 if issue.blocking else 0,
                        1 if issue.suggest_patch else 0,
                        issue.status,
                        json.dumps(issue.metadata or {}, ensure_ascii=False),
                        now,
                    ),
                )
            conn.execute(
                """
                UPDATE validation_reports
                SET status = ?,
                    passed = ?,
                    blocking_issue_count = ?,
                    p0_count = ?,
                    p1_count = ?,
                    p2_count = ?,
                    token_usage_json = ?,
                    updated_at = ?
                WHERE report_id = ?
                """,
                (
                    status,
                    1 if passed else 0,
                    blocking_issue_count,
                    grouped["P0"],
                    grouped["P1"],
                    grouped["P2"],
                    json.dumps(token_usage.__dict__, ensure_ascii=False),
                    now,
                    report_id,
                ),
            )
        return self.get_report(report_id)

    def get_report(self, report_id: str) -> Optional[ValidationReportDTO]:
        row = self.db.fetch_one("SELECT * FROM validation_reports WHERE report_id = ?", (report_id,))
        if not row:
            return None
        return self._build_report(row, self._list_issues(report_id))

    def get_latest_report(
        self,
        *,
        chapter_id: str,
        draft_type: str,
        draft_id: str | None = None,
    ) -> Optional[ValidationReportDTO]:
        params: List[Any] = [chapter_id, draft_type]
        sql = """
            SELECT * FROM validation_reports
            WHERE chapter_id = ? AND draft_type = ?
        """
        if draft_id:
            sql += " AND draft_id = ?"
            params.append(draft_id)
        sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 1"
        row = self.db.fetch_one(sql, tuple(params))
        if not row:
            return None
        return self._build_report(row, self._list_issues(row["report_id"]))

    def list_issues(
        self,
        *,
        novel_id: str | None = None,
        chapter_id: str | None = None,
        severity: str | None = None,
        status: str | None = None,
    ) -> List[ValidationIssueDTO]:
        clauses = []
        params: List[Any] = []
        sql = "SELECT vi.* FROM validation_issues vi"
        if novel_id:
            sql += " JOIN validation_reports vr ON vr.report_id = vi.report_id"
            clauses.append("vr.novel_id = ?")
            params.append(novel_id)
        if chapter_id:
            clauses.append("vi.chapter_id = ?")
            params.append(chapter_id)
        if severity:
            clauses.append("vi.severity = ?")
            params.append(severity)
        if status:
            clauses.append("vi.handling_status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY vi.created_at DESC"
        rows = self.db.fetch_all(sql, tuple(params))
        return [self._build_issue(row) for row in rows]

    def get_issue(self, issue_id: str) -> Optional[ValidationIssueDTO]:
        row = self.db.fetch_one("SELECT * FROM validation_issues WHERE issue_id = ?", (issue_id,))
        if not row:
            return None
        return self._build_issue(row)

    def update_issue_status(self, issue_id: str, status: str) -> ValidationIssueDTO:
        issue = self.get_issue(issue_id)
        if issue is None:
            raise ValueError("Validation issue not found")
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE validation_issues
                SET handling_status = ?
                WHERE issue_id = ?
                """,
                (status, issue_id),
            )
            conn.execute(
                """
                UPDATE validation_reports
                SET blocking_issue_count = (
                    SELECT COUNT(*)
                    FROM validation_issues
                    WHERE report_id = ?
                      AND blocking = 1
                      AND handling_status != 'resolved'
                ),
                    passed = CASE
                        WHEN (
                            SELECT COUNT(*)
                            FROM validation_issues
                            WHERE report_id = ?
                              AND blocking = 1
                              AND handling_status != 'resolved'
                        ) = 0 THEN 1
                        ELSE 0
                    END,
                    updated_at = ?
                WHERE report_id = ?
                """,
                (issue.report_id, issue.report_id, now, issue.report_id),
            )
        updated = self.get_issue(issue_id)
        if updated is None:
            raise ValueError("Validation issue not found")
        return updated

    def _list_issues(self, report_id: str) -> List[ValidationIssueDTO]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM validation_issues
            WHERE report_id = ?
            ORDER BY
                CASE severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
                created_at ASC
            """,
            (report_id,),
        )
        return [self._build_issue(row) for row in rows]

    def _build_report(self, row: Dict[str, Any], issues: List[ValidationIssueDTO]) -> ValidationReportDTO:
        return ValidationReportDTO(
            report_id=row["report_id"],
            chapter_id=row["chapter_id"],
            draft_type=row["draft_type"],
            draft_id=row["draft_id"],
            plan_version=int(row.get("plan_version") or 0),
            state_lock_version=int(row.get("state_lock_version") or 0),
            status=row.get("status") or "queued",
            passed=bool(row.get("passed")),
            blocking_issue_count=int(row.get("blocking_issue_count") or 0),
            p0_count=int(row.get("p0_count") or 0),
            p1_count=int(row.get("p1_count") or 0),
            p2_count=int(row.get("p2_count") or 0),
            token_usage=ValidationTokenUsageDTO.from_dict(json.loads(row.get("token_usage_json") or "{}")),
            issues=issues,
            created_at=self._parse_dt(row.get("created_at")),
            updated_at=self._parse_dt(row.get("updated_at")),
        )

    def _build_issue(self, row: Dict[str, Any]) -> ValidationIssueDTO:
        spans = [
            ValidationSpanDTO(
                paragraph_index=int(span.get("paragraph_index") or 0),
                start_offset=int(span.get("start_offset") or 0),
                end_offset=int(span.get("end_offset") or 0),
                excerpt=str(span.get("excerpt") or ""),
            )
            for span in json.loads(row.get("spans_json") or "[]")
        ]
        return ValidationIssueDTO(
            issue_id=row["issue_id"],
            report_id=row["report_id"],
            chapter_id=row["chapter_id"],
            severity=row["severity"],
            code=row["code"],
            title=row.get("title") or "",
            message=row.get("message") or "",
            spans=spans,
            blocking=bool(row.get("blocking")),
            suggest_patch=bool(row.get("suggest_patch")),
            status=row.get("handling_status") or "unresolved",
            metadata=json.loads(row.get("metadata_json") or "{}"),
        )

    @staticmethod
    def _parse_dt(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

