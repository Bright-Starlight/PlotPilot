CREATE TABLE IF NOT EXISTS state_locks (
    state_lock_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL UNIQUE,
    novel_id TEXT NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 0,
    latest_version INTEGER NOT NULL DEFAULT 0,
    plan_version INTEGER NOT NULL DEFAULT 1,
    time_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    location_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    character_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    item_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    numeric_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    event_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    ending_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    last_change_reason TEXT NOT NULL DEFAULT '',
    last_source TEXT NOT NULL DEFAULT 'generated',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS state_lock_versions (
    state_lock_version_id TEXT PRIMARY KEY,
    state_lock_id TEXT NOT NULL,
    chapter_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    plan_version INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'generated',
    change_reason TEXT NOT NULL DEFAULT '',
    changed_fields_json TEXT NOT NULL DEFAULT '[]',
    inference_notes_json TEXT NOT NULL DEFAULT '[]',
    critical_change_json TEXT NOT NULL DEFAULT '{}',
    time_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    location_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    character_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    item_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    numeric_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    event_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    ending_lock_json TEXT NOT NULL DEFAULT '{"entries":[]}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (state_lock_id) REFERENCES state_locks(state_lock_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_state_lock_versions_unique
    ON state_lock_versions(state_lock_id, version);
CREATE INDEX IF NOT EXISTS idx_state_locks_chapter
    ON state_locks(chapter_id);
CREATE INDEX IF NOT EXISTS idx_state_lock_versions_chapter
    ON state_lock_versions(chapter_id, version DESC);
