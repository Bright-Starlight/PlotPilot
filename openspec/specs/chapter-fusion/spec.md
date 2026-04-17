# chapter-fusion Specification

## Purpose
TBD - created by archiving change chapter-fusion. Update Purpose after archive.
## Requirements
### Requirement: Create fusion job
The system MUST allow a chapter fusion job to be created from a chapter plan version, state lock version, ordered beat IDs, target word count, and suspense budget.

#### Scenario: Create a queued fusion job
- **WHEN** the client submits a fusion job request with valid chapter and beat references
- **THEN** the system MUST create a fusion job record and return it in queued status

### Requirement: Validate fusion inputs
The system MUST block fusion job execution when required BeatDraft data or StateLocks data is missing, when the plan version is unavailable, or when the requested beats cannot be resolved.

#### Scenario: Missing beat drafts
- **WHEN** one or more requested beat drafts cannot be found
- **THEN** the system MUST refuse to start fusion and MUST mark the job as blocked

### Requirement: Generate fusion draft
The system MUST generate a FusionDraft by merging the source beats into a single chapter draft using the plan constraints, state locks, target word count, and suspense budget.

#### Scenario: Generate a draft from valid beats
- **WHEN** all required inputs are available
- **THEN** the system MUST produce a fusion draft for the chapter

### Requirement: Remove duplicate content
The system MUST deduplicate repeated functional content and repeated events across beats when producing the fusion draft.

#### Scenario: Duplicate recall appears in two beats
- **WHEN** two beats contain the same recall content
- **THEN** the fusion draft MUST keep the content once or merge it into a single natural expression

### Requirement: Preserve narrative continuity
The system MUST reorder or bridge content so the fusion draft remains narratively continuous across beat boundaries, including location or time jumps.

#### Scenario: Beats jump between locations
- **WHEN** adjacent beats move across locations without a natural bridge
- **THEN** the fusion draft MUST insert the necessary transition text

### Requirement: Enforce a single end state
The system MUST produce a fusion draft with one final end state that matches the planned chapter endpoint.

#### Scenario: Competing end states exist
- **WHEN** multiple beats imply different final locations or times
- **THEN** the fusion draft MUST resolve them into one end state and MUST mark the job as failed if a unique end state cannot be determined

### Requirement: Expose fusion quality signals
The system MUST record the fusion draft's repeat ratio, confirmed facts, open questions, end state, and warnings for downstream validation and review.

#### Scenario: Fusion completes successfully
- **WHEN** the fusion job finishes
- **THEN** the system MUST persist the fusion quality signals with the draft

### Requirement: Provide fusion preview data
The system MUST expose preview data for a fusion job, including estimated word count, estimated repeat ratio, expected end state, expected suspense count, and risk warnings.

#### Scenario: Preview before publish
- **WHEN** a user opens the fusion preview for a chapter
- **THEN** the system MUST return the preview summary before the draft is published

### Requirement: Support chapter workspace views
The system MUST provide chapter workspace views for beat drafts, the fusion draft, and a diff view between beat content and fusion output.

#### Scenario: Open chapter workspace
- **WHEN** a user opens a chapter after fusion runs
- **THEN** the system MUST make beat drafts, the fusion draft, and their diff view available

