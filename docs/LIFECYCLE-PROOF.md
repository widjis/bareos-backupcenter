# Lifecycle Proof Notes

This slice does **not** implement Disable/Enable execution. It adds a pure server-side proof normalizer for disable-schedule preview input.

## Purpose

`backend/lifecycle_proof.py` accepts trusted collector evidence and emits planner-compatible `snapshot` and `registry_evidence` only when the source is complete, current, and bound to the exact managed job requested. Otherwise it returns bounded blockers.

## Minimal trusted evidence contract

The current repository does not yet expose one authoritative collector schema for lifecycle disable proof, so the normalizer requires the following minimum structure:

- `trusted_role`: server-derived actor role (`Admin`, `Backup Operator`, or `Viewer`)
- `collector`: `{complete: true, revision: <int>}`
- `exact_job`:
  - `stable_id`
  - `job_name`
  - `selection_revision`
  - `snapshot_revision`
  - `identity_revision`
  - `repository_id`
  - `managed_vm_uuid` (exactly one persisted UUID; no fabrication)
  - `schedule`: `{resource_name, ownership, usage_count, proof_revision}`
- `registry`:
  - `revision`
  - `job_name`
  - `stable_id`
  - `repository_id`
  - `coverage`: exact sorted list `["dependencies","intents","operations","resources"]`
  - `enumerated`: explicit `True` flags for all four categories
  - explicit lists for `operations`, `dependencies`, `unresolved_intents`, and `resources`

## Fail-closed rules

The normalizer rejects:

- stale collector, snapshot, schedule, or registry revisions
- foreign job/repository bindings
- partial or implied enumeration
- missing exact schedule ownership proof
- multi-VM evidence
- non-dictionary or malformed trusted input

It never returns raw source error text. The exported `proof_digest` is bound to the full relevant evidence payload, including items beyond downstream display caps.

## Integration note

`backend.lifecycle_adapter.build_disable_preview(...)` remains the authoritative adapter. The normalizer only prepares trusted evidence for that adapter and planner path. To make collection trustworthy in production, the server still needs one reviewed query/registry source that can atomically provide:

1. current exact managed job identity and repository binding
2. exact schedule ownership at the same revision
3. fully enumerated current operations, dependencies, and unresolved intents
4. explicit completeness flags for those enumerations

## Coordinator review

Normalizer now rejects boolean/invalid revisions, truncated evidence, malformed planner identities, missing exact schedule rows and stale dependency/resource proof revisions. It does not create a schedule resource when the authoritative registry omits it. Full proof digest retains changes beyond output caps. Existing HTTP preview continues accepting only a scoped job name; this pure proof schema is not accepted from browser input and does not enable lifecycle mutations.
