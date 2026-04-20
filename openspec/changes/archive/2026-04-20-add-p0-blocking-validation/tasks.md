## 1. Validation Data Model

- [x] 1.1 Add `validation_reports` persistence with report summary fields, draft identity, input versions, and timestamps
- [x] 1.2 Add `validation_issues` persistence with severity, code, message, unified paragraph spans, blocking, patch eligibility, and resolution fields
- [x] 1.3 Add per-report LLM token usage fields and repository/query support for loading the latest report for a chapter draft and filtering issues by chapter, severity, and status

## 2. Validation Pipeline

- [x] 2.1 Implement the validation application service that loads `ChapterPlan`, `StateLocks`, `FactStore`, and `StoryBible` for a target draft
- [x] 2.2 Implement one shared span extraction and paragraph indexing path for both `FusionDraft` and `MergedDraft`
- [x] 2.3 Implement deterministic rule detectors for factual conflicts and other text-level blocking inconsistencies
- [x] 2.4 Implement state comparison checks for planned end state and current state lock consistency
- [x] 2.5 Integrate semantic judgment for identity drift and similar context-dependent issues, including eligibility rules and per-chapter token accounting
- [x] 2.6 Aggregate detector outputs into a normalized `ValidationReport` and persist report plus issues in one flow

## 3. APIs And Publish Gate

- [x] 3.1 Add `POST /api/chapters/{chapterId}/validate` to start validation and return report summary counts and status
- [x] 3.2 Add `GET /api/validation-reports/{reportId}` to return grouped P0, P1, and P2 issues with patch eligibility
- [x] 3.3 Add validation center query support for filtering issues by chapter, severity, and handling status, while disallowing P0 ignore as a bypass
- [x] 3.4 Trigger validation automatically after draft save using the current draft identity and input versions
- [x] 3.5 Enforce publish-time revalidation and publish blocking when the current draft has unresolved blocking issues or only stale validation reports

## 4. Frontend Validation Experience

- [x] 4.1 Add the chapter workspace Validation panel with grouped P0/P1/P2 sections, span highlights, blocking labels, patch action entry, and LLM token usage display
- [x] 4.2 Add the validation center page with chapter, severity, and status filters
- [x] 4.3 Update issue actions so P0 cannot be ignored through the UI while P1/P2 can still move to ignored
- [x] 4.4 Update the publish confirmation dialog to run revalidation, explain unresolved P0 failures, and disable publish while blocked

## 5. Patch Workflow And Quality Gates

- [x] 5.1 Add a repair-patch trigger path for issues marked `suggest_patch=true` without coupling it to the main validation request
- [x] 5.2 Add backend tests for factual conflict, non-unique ending, identity drift, token usage recording, and P0 ignore rejection
- [x] 5.3 Add frontend tests for workspace highlighting, validation center filtering, automatic validation refresh, and publish blocking behavior
