# Lifecycle Batch 5 Acceptance Review

Later coordinator checkpoint: see LIFECYCLE-LOCAL-ACCEPTANCE.md. The findings below are retained interim review evidence; several local receipt/dependency/read-back issues were subsequently corrected and tested. Complete native coverage and production acceptance remain open.

Status: **interim targeted review of the new execution candidates**

I kept this pass narrow: `integration/apply_job_lifecycle.py`, `backend/lifecycle_target.py`, `backend/lifecycle_manager.py`, their worker/persistence call sites, and existing lifecycle proof tests. I waited once for `.local/lifecycle-batch5/backend-result.json` with a bounded 20-second sleep; it still did not exist, so this is not a final peer-complete acceptance.

Checks run:

- `& ".venv\\Scripts\\python.exe" -m pytest -q backend/tests/test_job_lifecycle.py backend/tests/test_lifecycle_proof.py backend/tests/test_lifecycle_collector.py backend/tests/test_lifecycle_adapter.py` -> **41 passed**
- `& ".venv\\Scripts\\python.exe" -m py_compile backend/lifecycle_manager.py backend/lifecycle_target.py integration/apply_job_lifecycle.py` -> **passed**

No remote mutation, no backup/restore, no job/config deletion, and no ordinary `21:30` acceptance were executed.

## Interim observations

- The repo now contains a real lifecycle helper candidate ([`integration/apply_job_lifecycle.py`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py)) plus backend orchestration ([`backend/lifecycle_manager.py`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_manager.py)).
- I did **not** find dedicated execution tests for the new helper/manager/target path yet; current passing tests still cover the proof/planner slice only.

## Findings

1. **Critical: disable read-back is internally inconsistent and is likely to self-fail after mutation**
   - Evidence: [`_read_state()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L48-L102) always runs `verify_retry_directives` and `verify_hooks` before returning current state. [`_apply_disable()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L125-L143) then removes `Schedule`, clears retry directives, and drops the dependency block from the source job. After writing those changes, [`apply()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L196-L205) calls `current(job_name)` again for validation.
   - Impact: the same helper that disables hooks/retry may reject the disabled state during its own reread, causing rollback or `Unknown` even when the intended disable succeeded on disk.
   - Minimal remedy: add a lifecycle-aware current/read-back mode for disabled targets instead of reusing the normal enabled-policy verifiers unchanged.

2. **High: resource proof and managed scope are still hardcoded, not authoritative**
   - Evidence: [`_read_state()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L48-L75) rejects any job outside `NAMES` and hardcodes `job`, `pool`, and `fileset` as `ownership="exclusive"` with `usage_count=1`. Schedule sharing is counted only by scanning `sorted(NAMES)` rather than the full Director config.
   - Impact: lifecycle review can falsely claim exclusive ownership, miss non-`NAMES` references, and overstate clone/remove safety. This does not meet the authoritative-proof requirement for shared resources or preserved recovery discovery.
   - Minimal remedy: collect resource ownership from the full Director configuration plus persisted managed assignment identity, not from the fixed helper allowlist.

3. **High: runtime/deferred-delivery guards are still incomplete before mutation**
   - Evidence: [`review_disable()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_manager.py#L53-L123) feeds planner operations from database journal rows only via [`_ops()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_manager.py#L35-L46) and passes `unresolved_intents: []` at [L103](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_manager.py#L103). [`prepare_lifecycle()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/persistence.py#L287-L288) blocks unresolved DB lifecycle operations, but [`apply()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L171-L221) performs filesystem mutation without any guard for queued/deferred after-job receipts or disabled-target runtime state.
   - Impact: a job can be marked disabled while previously queued runtime work is still eligible to dispatch, which would let the old after-job path race with lifecycle disable.
   - Minimal remedy: before any lifecycle write, query runtime pending/active receipts for the target and relevant sources, then fail closed until those receipts are drained or retired.

4. **High: receipt durability and rollback evidence are not crash-safe or strongly bound**
   - Evidence: [`apply()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L184-L220) writes a receipt in `Dispatching` state before persisting any before-image, keeps `before` only in memory, and never fsyncs the receipt or the saved originals. Receipt replay only checks `reviewDigest`, `action`, and `jobName` at [L177-L180](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L177-L180); it does not bind actor or prepared revision metadata into the helper receipt itself.
   - Impact: a process crash after partial writes can leave no durable rollback payload on disk even though the receipt already exists. The receipt also does not independently prove which actor/revision created the mutation.
   - Minimal remedy: persist root-owned before-images and actor/revision binding to the receipt before the first write, fsync them, then mutate and verify.

5. **Medium: readiness reporting is still misleading for native prerequisites**
   - Evidence: [`current()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/integration/apply_job_lifecycle.py#L105-L107) always returns `executionReady: True` / `candidate_ready` without checking root execution, receipt directory integrity, installed helper prerequisites, or unresolved helper receipts. [`candidate_capabilities()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_target.py#L15-L22) always reports `candidateReady: True`; if `BACKUPCENTER_LIFECYCLE_APPLY_ENABLED=1`, it also clears `liveApplyBlocker` even though [`invoke()`](file:///c:/Scripts/Projects/bareos/bareos-backupcenter/backend/lifecycle_target.py#L7-L12) still raises for every action in this Windows environment.
   - Impact: UI/backend state can imply execution readiness before a real native transport/prerequisite check has passed.
   - Minimal remedy: keep the blocker explicit until transport invocation, root execution, receipt safety, and installed-helper readiness are all verified.

## Bottom line

This is meaningful progress beyond the old pure preview slice, but it is **not yet ready to be described as authoritative lifecycle execution**. The helper/manager candidate now exists, yet the remaining blockers are exactly in the areas that matter most for safe Disable/Enable: disabled-state read-back, authoritative ownership proof, runtime receipt suppression, crash-safe rollback, and truthful readiness reporting.
