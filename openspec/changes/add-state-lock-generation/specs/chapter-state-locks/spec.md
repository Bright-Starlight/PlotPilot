## ADDED Requirements

### Requirement: Generate chapter state locks before downstream draft stages
The system MUST generate an initial `StateLocks` snapshot for a chapter before any downstream draft stage that depends on chapter facts, including BeatDraft generation, chapter fusion, validation, patch, or merge.

#### Scenario: Generate initial state locks for a chapter
- **WHEN** the client requests state lock generation for a chapter with an available plan context
- **THEN** the system MUST read the previous chapter end state, `ChapterPlan`, `FactStore`, and `StoryBible`, and MUST create an initial `StateLocks` snapshot

#### Scenario: Rebuild state locks from a specified plan version
- **WHEN** the client requests state lock generation for a chapter and specifies a `plan_version`
- **THEN** the system MUST generate a new `state_lock_version` from that specified plan version instead of implicitly switching to the latest plan version

### Requirement: Use LLM only for hard-to-determine lock inference
The system MUST prefer deterministic sources and rules when generating state locks, and MAY invoke LLM assistance only for lock inference steps that cannot be judged reliably through rules alone, such as alias resolution, implicit status extraction, or ambiguous end-state normalization.

#### Scenario: Resolve an ambiguous ending lock with LLM assistance
- **WHEN** available chapter context contains multiple textual descriptions of the likely ending state and the system cannot derive one stable ending lock through rules alone
- **THEN** the system MUST allow an LLM-assisted inference step to produce a structured ending lock candidate before saving the versioned state lock snapshot

### Requirement: Persist versioned state lock snapshots
The system MUST persist each generated or manually edited state lock set as a new versioned snapshot and MUST keep the full snapshot content for audit and replay.

#### Scenario: Save a new state lock version after manual edit
- **WHEN** a user updates any state lock field and provides a modification reason
- **THEN** the system MUST create a new state lock version with the full snapshot, increment the version number, and preserve the previous versions

### Requirement: Expose current chapter state locks
The system MUST expose the current state lock set for a chapter, including the stable state lock ID, current version number, and grouped lock content.

#### Scenario: Retrieve current state locks
- **WHEN** the client requests the current state locks for a chapter
- **THEN** the system MUST return the current `state_lock_id`, current `version`, and grouped lock fields for that chapter

### Requirement: Support grouped lock categories
The system MUST represent state locks with explicit grouped categories for time, location, character, item, numeric, event, and ending constraints.

#### Scenario: Return grouped lock payload
- **WHEN** the system returns a state lock payload
- **THEN** the payload MUST preserve separate `time_lock`, `location_lock`, `character_lock`, `item_lock`, `numeric_lock`, `event_lock`, and `ending_lock` groups

### Requirement: Persist structured lock results after LLM-assisted inference
The system MUST convert any LLM-assisted lock inference output into the same structured lock schema used by deterministic generation, and downstream stages MUST consume only the saved structured state lock version.

#### Scenario: Fusion consumes a lock generated with LLM assistance
- **WHEN** a state lock version was created using LLM assistance for one or more lock fields
- **THEN** the system MUST save those fields in the standard structured lock payload and MUST require fusion to consume the saved version rather than rerunning inference

### Requirement: Require version-aware lock edits
The system MUST require a change reason for manual state lock edits and MUST surface whether a lock entry is normal, manually modified, or violated by downstream text.

#### Scenario: Edit ending lock with reason
- **WHEN** a user changes the ending lock target in the editor
- **THEN** the system MUST reject the update if no reason is provided, and MUST mark the changed lock entry as manually modified in subsequent reads

### Requirement: Bind downstream stages to one state lock version
The system MUST require BeatDraft, Fusion, Validation, Patch, and Merge records or jobs to reference an explicit `state_lock_version`, and those stages MUST read the same referenced version instead of implicitly resolving the chapter's latest lock version.

#### Scenario: Validation reads the same lock version as fusion
- **WHEN** a validation task runs for a fusion draft that references `state_lock_version = 5`
- **THEN** the validation task MUST load version `5` of the chapter state locks rather than any newer current version

#### Scenario: Beat draft binds the same lock version as downstream stages
- **WHEN** beat drafts are generated for a chapter after state locks are created
- **THEN** each beat draft record MUST store the explicit `state_lock_version` it consumed so fusion and validation can reuse the same version

### Requirement: Mark downstream fusion drafts stale after critical lock changes
The system MUST detect whether a new state lock version changes critical lock domains, including ending locks, critical numeric locks, character inclusion or exclusion, or forbidden events, and MUST mark affected existing fusion drafts as stale or needing refusion.

#### Scenario: Ending lock change invalidates an existing fusion draft
- **WHEN** a new state lock version changes the required ending lock for a chapter that already has a fusion draft
- **THEN** the system MUST mark the affected fusion draft as `stale` or `needs_refusion`

### Requirement: Surface state lock violations for downstream text
The system MUST allow downstream text review surfaces to flag when generated chapter text violates the bound state locks and MUST provide a link or reference back to the violated lock entry.

#### Scenario: Text violates a forbidden character lock
- **WHEN** chapter text includes a character that is forbidden by the bound character lock
- **THEN** the system MUST surface a state lock violation indicator and MUST provide navigation to the violated lock detail
