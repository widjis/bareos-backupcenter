# Lifecycle Batch 5 Contract

This document defines the intended backend contract for lifecycle work in this batch only. It does not claim live scheduling acceptance, helper deployment readiness, or production authorization.

Current implementation status in this slice:

- Disable / Enable review and durable candidate apply path: implemented
- Clone / Remove preserve-backups: contract remains planned, not yet exposed as durable apply in this slice

## Scope

- Disable / Enable a managed job schedule without deleting backups
- Edit per-job schedule/settings using the existing single-job policy owner
- Clone a managed job into a disabled reviewed draft
- Remove managed job configuration while preserving retained backups by default

Unsupported in this batch:

- backup-data deletion
- multi-VM regrouping
- secret copying
- unreviewed job/VM/repository reassignment when ownership proof is missing

## Shared rules

All lifecycle mutations are Admin-only, same-origin, confirmed actions using durable idempotency keys, review digests, revision checks, audit entries, rollback/read-back verification, and no automatic redispatch after Unknown delivery.

All review endpoints are read-only and must fail closed on missing identity, missing ownership proof, stale revisions, active/waiting operations, unresolved inbound dependencies, or retained-recovery proof gaps.

`readiness` is one of:

- `blocked`: missing proof, unsupported request, stale revision, active dependency, shared resource, or server prerequisite missing
- `review_only`: request can be reviewed locally but execution remains disabled
- `candidate_ready`: backend/native candidate logic is internally consistent, but live deployment/acceptance still separate

Frontend must never infer `candidate_ready` means accepted for production use.

## Intended endpoints

### Disable / Enable

- `POST /api/jobs/lifecycle/disable/review`
- `POST /api/jobs/lifecycle/disable`
- `POST /api/jobs/lifecycle/enable/review`
- `POST /api/jobs/lifecycle/enable`

Review request:

- `jobName`

Review response:

- `jobName`
- `action`
- `readiness`
- `reviewDigest`
- `proofRevision`
- `blockers[]`
- `impacts[]`
- `summary`
- `executionSupported`

Apply request:

- `jobName`
- `reviewDigest`
- `proofRevision`
- `idempotencyKey`
- `confirmed`

Apply response:

- durable operation record with `id`, `state`, `kind`, `target`, `parameters`

Disable must suppress automatic calendar, after-job, and retry delivery without deleting recovery evidence. Enable must restore the previously owned reviewed schedule/hooks only when read-back identity still matches.

### Edit per-job

Reuse existing:

- `GET /api/policies/active/current?jobName=...`
- `POST /api/policies/active/preview`
- `POST /api/policies/active/apply`

This batch may broaden backend proof/readiness semantics, but must preserve the existing request body shape used by the current per-job schedule flow.

### Clone

- `POST /api/jobs/lifecycle/clone/review`
- `POST /api/jobs/lifecycle/clone`

Review request:

- `sourceJobName`
- `newJobName`

Review response adds:

- `draftPlan`
- `resourceOwnership`
- `duplicateProtection`
- `unsupportedChanges[]`

Clone must default to disabled scheduling and must not copy secrets, recovery history, or unsafe exclusive mappings.

### Remove configuration, preserve backups

- `POST /api/jobs/lifecycle/remove/review`
- `POST /api/jobs/lifecycle/remove`

Review request:

- `jobName`

Review response adds:

- `preserveBackupData: true`
- `retainedRecovery`
- `retirementRecord`
- `retainedObligations[]`

Removal must create the retirement record first, block on unsupported dependencies/shared ownership, and must not purge Catalog rows, volumes, or backup files.

## Result polling

Frontend should continue using the existing durable operation/result patterns. `Unknown` delivery remains a reconciliation state, not success and not permission to resend automatically.

This slice also exposes `GET /api/jobs/lifecycle/status/{requestId}` for the durable disable/enable candidate receipt.
