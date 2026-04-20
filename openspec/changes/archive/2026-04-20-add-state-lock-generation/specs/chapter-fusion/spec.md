## MODIFIED Requirements

### Requirement: Create fusion job
The system MUST allow a chapter fusion job to be created from a chapter plan version, an explicit previously generated state lock version, ordered beat IDs, target word count, and suspense budget.

#### Scenario: Create a queued fusion job
- **WHEN** the client submits a fusion job request with valid chapter and beat references and a valid generated `state_lock_version`
- **THEN** the system MUST create a fusion job record, bind it to that state lock version, and return it in queued status

### Requirement: Validate fusion inputs
The system MUST block fusion job execution when required BeatDraft data or StateLocks data is missing, when the plan version is unavailable, when the requested beats cannot be resolved, or when no valid previously generated state lock version is provided for the chapter.

#### Scenario: Missing beat drafts
- **WHEN** one or more requested beat drafts cannot be found
- **THEN** the system MUST refuse to start fusion and MUST mark the job as blocked

#### Scenario: Missing state lock version before fusion
- **WHEN** a client attempts to start chapter fusion without a generated state lock version for the chapter
- **THEN** the system MUST refuse to start fusion and MUST return that state locks must be generated before fusion can run

## ADDED Requirements

### Requirement: Preserve state lock version contract across fusion output
The system MUST persist the `state_lock_version` consumed by fusion on the resulting fusion draft and MUST expose that version for downstream validation and publish checks.

#### Scenario: Read fusion draft with bound state lock version
- **WHEN** a client reads a completed fusion draft
- **THEN** the system MUST return the fusion draft together with the exact `state_lock_version` used to generate it

### Requirement: Expose stale fusion state after critical lock updates
The system MUST expose when an existing fusion draft is no longer trustworthy because a newer state lock version changed a critical lock domain that affects fusion output.

#### Scenario: Chapter workspace reads a stale fusion draft
- **WHEN** a fusion draft has been marked `stale` or `needs_refusion` after a critical state lock update
- **THEN** the system MUST expose that stale status so the client can prevent users from treating the draft as current
