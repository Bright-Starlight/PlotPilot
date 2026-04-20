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

## ADDED Requirements

### Requirement: Block chapter publish on unresolved validation failures
The system MUST prevent a chapter draft from entering publish state when the current draft has unresolved blocking validation issues.

#### Scenario: Prevent publish with unresolved P0 issues
- **WHEN** the current draft's latest matching validation report contains one or more unresolved issues with `blocking` set to `true`
- **THEN** the system MUST reject the publish action and MUST return the reason that publish is blocked by validation failures

### Requirement: Show validation status in chapter workspace
The system MUST show validation results for the current chapter draft in the chapter workspace, grouped by P0, P1, and P2 severity.

#### Scenario: Display validation panel in the chapter workspace
- **WHEN** a user opens a chapter workspace for a draft that has validation results
- **THEN** the workspace MUST display a validation panel with issue title, affected paragraph spans, blocking state, and patch generation entry for repairable issues

### Requirement: Require a current validation report for publish confirmation
The system MUST verify that the validation report used for publish confirmation matches the current draft identifier and validation input versions.

#### Scenario: Reject publish when the report is stale
- **WHEN** the latest available validation report was generated for a different draft identifier, plan version, or state lock version than the current publish target
- **THEN** the system MUST require validation to be re-run before publish can proceed

### Requirement: Force validation before publish
The system MUST trigger a fresh validation run for the current chapter draft as part of the publish confirmation flow before allowing publish to continue.

#### Scenario: Revalidate before publish
- **WHEN** a user enters the publish confirmation flow for a chapter draft
- **THEN** the system MUST run validation against the current draft and use that result as the final publish gate
