CREATE TABLE IF NOT EXISTS chapter_draft_bindings (
    chapter_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    draft_type TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    plan_version INTEGER NOT NULL,
    state_lock_version INTEGER NOT NULL,
    source_fusion_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chapter_id, draft_type, draft_id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chapter_draft_bindings_chapter_type
    ON chapter_draft_bindings(chapter_id, draft_type, updated_at DESC);
