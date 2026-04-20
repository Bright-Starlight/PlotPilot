## 1. Data Model And APIs

- [x] 1.1 Create `state_locks` and `state_lock_versions` persistence models with grouped lock payload fields and version indexes
- [x] 1.2 Implement `POST /api/chapters/{chapterId}/state-locks` to generate an initial state lock snapshot from previous chapter end state, `ChapterPlan`, `FactStore`, and `StoryBible`, with support for a specified `plan_version`
- [x] 1.3 Implement `GET /api/chapters/{chapterId}/state-locks/current` to return the current `state_lock_id`, version, grouped locks, and lock entry statuses
- [x] 1.4 Implement `PATCH /api/state-locks/{stateLockId}` to require a change reason and persist a new full snapshot version after manual edits

## 2. Lock Generation And Version Binding

- [x] 2.1 Build the state lock generation service to derive time, location, character, item, numeric, event, and ending locks from chapter context
- [x] 2.2 Add an LLM-assisted inference path for alias resolution, ambiguous ending-state normalization, and implicit fact extraction when rule-based generation cannot decide reliably
- [x] 2.3 Record manual modification metadata and expose lock entry statuses as `normal`, `violated`, or `manually_modified`
- [x] 2.4 Update BeatDraft, Fusion, Validation, Patch, and Merge records or job payloads to store an explicit `state_lock_version`
- [x] 2.5 Add guards that reject downstream stage execution when the referenced `state_lock_version` is missing or invalid
- [x] 2.6 Add lock-version diff detection for critical domains and mark affected FusionDraft records as `stale` or `needs_refusion`

## 3. Fusion And Validation Integration

- [x] 3.1 Update fusion job creation to require a previously generated `state_lock_version` and persist that version on the resulting fusion draft
- [x] 3.2 Remove any implicit “use latest chapter state” fallback from fusion input resolution
- [x] 3.3 Align validation input loading with fusion draft metadata so validation reads the same bound `state_lock_version`
- [x] 3.4 Surface structured state lock violations for forbidden characters, numeric conflicts, and ending lock deviations so downstream P0 validation can block publish

## 4. Workspace UX

- [x] 4.1 Add a State Locks card to the chapter workspace right rail with grouped lock sections and per-entry status display
- [x] 4.2 Add a state lock editor modal that supports advanced edits, requires a change reason, and creates a new version on save
- [x] 4.3 Add violation highlighting and lock-detail navigation from chapter text or validation views when a state lock is violated
- [x] 4.4 Show when newer state lock versions exist so users can see that an existing fusion draft may need regeneration
