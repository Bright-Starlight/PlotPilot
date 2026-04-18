## ADDED Requirements

### Requirement: Start chapter draft validation
The system MUST allow a client to start validation for a chapter `FusionDraft` or `MergedDraft` by chapter, draft type, draft identifier, plan version, and state lock version.

#### Scenario: Start validation for a fusion draft
- **WHEN** the client submits `POST /api/chapters/{chapterId}/validate` with a valid `fusion` draft reference and input versions
- **THEN** the system MUST create a validation report for that chapter and return the report identifier, execution status, pass flag, and P0/P1/P2 counts

#### Scenario: Auto-trigger validation after draft save
- **WHEN** a chapter draft is saved successfully
- **THEN** the system MUST automatically start a validation run for the saved draft using the current draft identity and input versions

### Requirement: Run layered blocking consistency checks
The system MUST execute chapter validation in three layers: rule detection, state comparison, and semantic judgment, using `ChapterPlan`, `StateLocks`, `FactStore`, and `StoryBible` as validation context.

#### Scenario: Detect a deterministic factual conflict
- **WHEN** the draft contains mutually exclusive factual statements such as the same jade pendant being pawned for both three taels and fifty taels
- **THEN** the rule detection layer MUST record a blocking P0 issue for the factual conflict

#### Scenario: Detect a conflicting chapter end state
- **WHEN** the draft ends in two mutually exclusive terminal states that cannot both satisfy the planned chapter endpoint
- **THEN** the state comparison layer MUST record a blocking P0 issue for non-unique end state

#### Scenario: Escalate identity drift through semantic judgment
- **WHEN** the draft refers to a character with a new identity that cannot be justified by the current story context but requires semantic resolution rather than deterministic matching
- **THEN** the semantic judgment layer MUST classify the issue as P0 or P1 and MUST mark it blocking when the drift breaks chapter continuity

### Requirement: Use a unified paragraph span model
The system MUST use one shared span location model for both `FusionDraft` and `MergedDraft` so that validation, diff display, patch generation, and frontend highlighting can reuse the same paragraph references.

#### Scenario: Return spans for different draft types
- **WHEN** validation reports issues for either a `FusionDraft` or a `MergedDraft`
- **THEN** the report MUST express affected locations with the same span schema and paragraph indexing rules

### Requirement: Apply bounded LLM semantic judgment
The system MUST restrict LLM semantic judgment to issue classes that cannot be resolved deterministically and MUST track per-chapter token usage for semantic judgment.

#### Scenario: Use LLM only for eligible semantic issues
- **WHEN** validation encounters a deterministic factual or state mismatch
- **THEN** the system MUST classify the issue without calling the LLM semantic judgment gateway

### Requirement: Record and expose semantic token consumption
The system MUST record per-chapter LLM semantic judgment token consumption and expose that usage to clients for validation report visibility.

#### Scenario: Show token consumption in validation results
- **WHEN** a validation run uses the LLM semantic judgment gateway
- **THEN** the system MUST persist the run's token usage summary and include it in the validation data returned to the frontend

### Requirement: Persist structured validation reports
The system MUST persist each validation run as a report with issue records that capture severity, code, title, message, spans, blocking flag, patch suggestion flag, and resolution status.

#### Scenario: Save issues for a completed report
- **WHEN** a validation run completes
- **THEN** the system MUST save one `validation_reports` record and one or more related `validation_issues` records for every detected issue

### Requirement: Return validation report details
The system MUST expose report details through `GET /api/validation-reports/{reportId}` and group the returned issues by P0, P1, and P2 severity.

#### Scenario: Fetch report detail for a blocking report
- **WHEN** the client requests a completed report that contains blocking issues
- **THEN** the system MUST return the report metadata and include each P0 issue's code, title, message, spans, blocking flag, and patch suggestion flag

### Requirement: Support validation issue review workflows
The system MUST allow clients to review validation issues by chapter, severity, and handling status, including unresolved, resolved, and ignored states.

#### Scenario: Filter issues in the validation center
- **WHEN** a user opens the validation center and filters by chapter, severity, or issue status
- **THEN** the system MUST return only the matching validation issues and their associated report context

### Requirement: Forbid ignoring blocking P0 issues
The system MUST prevent blocking P0 issues from being marked ignored for publish purposes.

#### Scenario: Reject ignore on a P0 issue
- **WHEN** a client attempts to mark a blocking P0 issue as ignored
- **THEN** the system MUST reject the state change or keep the issue in a publish-blocking state

### Requirement: Offer patch generation for repairable issues
The system MUST identify which validation issues can request a repair patch and expose that eligibility to the client.

#### Scenario: Show patch generation eligibility for a blocking conflict
- **WHEN** a validation issue is marked as repairable by the validation pipeline
- **THEN** the report detail response MUST set `suggest_patch` to `true` for that issue so the client can render a patch generation action
