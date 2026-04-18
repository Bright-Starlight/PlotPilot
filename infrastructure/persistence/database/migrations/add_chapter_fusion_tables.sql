CREATE TABLE IF NOT EXISTS fusion_jobs (
    fusion_job_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    state_lock_version INTEGER NOT NULL,
    beat_ids_json TEXT NOT NULL DEFAULT '[]',
    target_words INTEGER NOT NULL DEFAULT 0,
    suspense_budget_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapter_fusion_drafts (
    fusion_id TEXT PRIMARY KEY,
    fusion_job_id TEXT NOT NULL UNIQUE,
    chapter_id TEXT NOT NULL,
    source_beat_ids_json TEXT NOT NULL DEFAULT '[]',
    plan_version INTEGER NOT NULL,
    state_lock_version INTEGER NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    repeat_ratio REAL NOT NULL DEFAULT 0.0,
    facts_confirmed_json TEXT NOT NULL DEFAULT '[]',
    open_questions_json TEXT NOT NULL DEFAULT '[]',
    end_state_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    state_lock_violations_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fusion_job_id) REFERENCES fusion_jobs(fusion_job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fusion_job_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fusion_job_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fusion_job_id) REFERENCES fusion_jobs(fusion_job_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fusion_jobs_chapter ON fusion_jobs(chapter_id);
CREATE INDEX IF NOT EXISTS idx_fusion_job_logs_job ON fusion_job_logs(fusion_job_id, id);

CREATE TABLE IF NOT EXISTS beat_sheets (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
