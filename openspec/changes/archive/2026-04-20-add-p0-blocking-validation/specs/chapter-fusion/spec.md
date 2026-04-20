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
