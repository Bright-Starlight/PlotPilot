## 1. Data Model and Contracts

- [x] 1.1 Add fusion job and fusion draft DTOs/contracts for create, status, and result payloads.
- [x] 1.2 Add persistence support for `chapter_fusion_drafts` and `fusion_job_logs`.
- [x] 1.3 Add status fields and JSON columns needed for repeat ratio, facts, open questions, end state, and warnings.

## 2. Fusion Pipeline and API

- [x] 2.1 Implement the chapter fusion service that reads ChapterPlan, BeatDrafts, StateLocks, target words, and suspense budget.
- [x] 2.2 Implement deduplication, transition bridging, end-state unification, and length trimming in the fusion pipeline.
- [x] 2.3 Add `POST /api/chapters/{chapterId}/fusion-jobs` to create a queued fusion job.
- [x] 2.4 Add `GET /api/fusion-jobs/{fusionJobId}` to return job status and the FusionDraft payload.
- [x] 2.5 Persist fusion step logs for blocked, running, completed, warning, and failed states.

## 3. Validation and Chapter Workspace

- [x] 3.1 Connect FusionDraft validation so repeat ratio, end-state uniqueness, and required fields gate downstream publishing.
- [x] 3.2 Expose preview data for estimated words, repeat ratio, end state, suspense count, and risk warnings.
- [x] 3.3 Add chapter workspace tabs for Beat Drafts, Fusion Draft, and Beat-vs-Fusion diff.
- [x] 3.4 Add the fusion preview modal and repeat-function warning display in the beat workbench.

## 4. Tests and Acceptance Coverage

- [x] 4.1 Add backend tests for missing BeatDrafts and missing StateLocks blocking fusion.
- [x] 4.2 Add backend tests for duplicate recall deduplication and transition insertion across location jumps.
- [x] 4.3 Add backend tests for single end-state enforcement and failed output when the end state cannot be unified.
- [x] 4.4 Add frontend tests for the fusion preview, workspace tabs, and warning states.
