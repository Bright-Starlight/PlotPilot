CREATE TABLE IF NOT EXISTS validation_reports (
    report_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    draft_type TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    state_lock_version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    passed INTEGER NOT NULL DEFAULT 0,
    blocking_issue_count INTEGER NOT NULL DEFAULT 0,
    p0_count INTEGER NOT NULL DEFAULT 0,
    p1_count INTEGER NOT NULL DEFAULT 0,
    p2_count INTEGER NOT NULL DEFAULT 0,
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS validation_issues (
    issue_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    spans_json TEXT NOT NULL DEFAULT '[]',
    blocking INTEGER NOT NULL DEFAULT 0,
    suggest_patch INTEGER NOT NULL DEFAULT 0,
    handling_status TEXT NOT NULL DEFAULT 'unresolved',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES validation_reports(report_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_validation_reports_chapter_draft
    ON validation_reports(chapter_id, draft_type, draft_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_validation_issues_report
    ON validation_issues(report_id);
CREATE INDEX IF NOT EXISTS idx_validation_issues_filters
    ON validation_issues(chapter_id, severity, handling_status);
