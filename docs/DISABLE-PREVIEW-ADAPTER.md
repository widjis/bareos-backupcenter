# Disable Preview Adapter

`backend/lifecycle_adapter.py` adds a small fail-closed adapter for P07-045B:

- Function: `build_disable_preview(snapshot, job_name, *, trusted_role, registry_evidence=None)`
- Scope: disable-schedule preview only
- Mode: pure read-only
- Execution: always `executionSupported=False`

## Normalized trusted input contract

The adapter intentionally accepts only normalized server-owned evidence. It does not translate arbitrary request payloads into trusted proof.

Required `snapshot` keys:

- `stable_id`
- `job_name`
- `selection_revision`
- `snapshot_revision`
- `identity_revision`
- `managed_vm_ids`
- `repository_id`

Optional snapshot keys:

- `actor_role`: legacy fixture label only
- `source_error`: explicit source/connection failure marker

Required `registry_evidence` keys:

- `proof_revision`
- `proof_coverage`
- `resources`

Optional normalized evidence lists:

- `operations`
- `dependencies`
- `unresolved_intents`

`proof_coverage` must explicitly contain exactly `operations`, `dependencies`, `intents`, and `resources`. The adapter treats missing or partial coverage as untrusted. An empty list never implies a checked registry.

## Behavior

The adapter returns a bounded result:

- `jobName`
- `action`
- `executionSupported`
- `blockers`
- `impacts`
- `digest`

It fails closed before planner invocation when:

- the requested job is not proven by the snapshot
- the snapshot is partial or stale
- a source/connection error is present
- registry evidence is missing, incomplete, stale, or lacks reviewed schedule bindings

Only after those checks pass does it call the existing pure planner in `backend/job_lifecycle.py`. `trusted_role` is authoritative and stays separate from any `actor_role` found inside the snapshot, so forged snapshot role labels cannot elevate permission.

The adapter excludes secrets, raw job configuration, transport details, endpoints, and execution paths. Live evidence collection, authoritative registry builders, API wiring, and actual Disable execution remain separate follow-up work.

Coordinator verification: full backend suite passed (155 passed, 1 POSIX-only skipped). Authoritative operations, dependencies and unresolved-intent lists must be explicitly supplied; missing lists cannot default to empty proof. Invalid planner evidence produces a blocker, and raw source diagnostics are withheld. No HTTP/UI route or execution is enabled.
