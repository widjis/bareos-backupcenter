# Disable Collector

`backend/lifecycle_collector.py` adds `collect_disable_preview(snapshot, job_name, *, trusted_role)` for the existing disable-preview route import, but it stays intentionally conservative.

## Current behavior

- Input must be the real monitoring snapshot shape from `backend/app.py`.
- Job lookup uses the exact `snapshot["jobs"][*]["name"]` value only.
- Output is bounded and read-only:
  - `jobName`
  - `action`
  - `executionSupported` = `false`
  - `blockers`
  - `impacts`
  - `digest`
- The collector never returns raw snapshot data, config text, diagnostics, or secrets.
- `trusted_role` is authoritative and is never taken from snapshot content.

## Why it blocks

The monitoring snapshot and persisted workload cache are useful for exact job discovery, stale/partial detection, and persistence-state checks, but they do **not** authoritatively prove the lifecycle planner inputs required by `backend.lifecycle_adapter` / `backend.job_lifecycle`.

The collector therefore fails closed and reports missing proof instead of inventing:

- stable managed identity
- managed VM assignment UUIDs
- repository binding identifiers
- selection/snapshot/identity revisions
- schedule ownership / exclusivity
- durable active operations, dependencies, or unresolved intents

It reuses the existing adapter only for bounded fail-closed normalization feedback where that helps, then adds explicit blockers for the missing authoritative collectors.

## Required future authoritative collectors

1. **Stable identity collector**  
   Read server-owned assignment/revision state and prove exact job -> stable managed identity, managed VM assignment, repository binding, and current identity revision.

2. **Resource ownership collector**  
   Read current configuration revisions or live apply receipts and prove the schedule/resource bindings, ownership, exclusivity, and usage counts for the target job.

3. **Lifecycle registry collector**  
   Read durable application journals and prove current operations, dependencies, and unresolved intents without relying on bounded monitoring sessions.

Until those collectors exist, Disable preview remains informative only and must not imply execution readiness.

Coordinator integrated the collector behind an Admin-only, same-origin, exact managed-scope POST and the Jobs read-only review dialog. Trusted Viewer roles are explicitly blocked independently of snapshot labels. Missing authoritative collectors remain blockers; this integration does not enable Disable execution.
