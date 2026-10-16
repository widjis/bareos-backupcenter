# Lifecycle Native Execution

This batch delivers the native execution adapters and local helper hardening needed for production-bound lifecycle apply paths without enabling live mutation by default.

## Delivered components

- `backend/lifecycle_target.py`
  - Uses the fixed `C:\Scripts\Projects\bareos\Invoke-BareosRemote.ps1` wrapper on Windows hosts.
  - Sends bounded JSON requests as base64 over stdin to avoid shell interpolation and command injection.
  - Routes clone and retirement actions to `/opt/bareos-api/lifecycle_resource_executor.py`.
  - Routes disable, enable, review, current, and status actions to `/opt/bareos-api/apply_job_lifecycle.py`.
  - Reads real capability responses instead of treating `os.name == "posix"` or an env flag as sufficient readiness.

- `integration/apply_job_lifecycle.py`
  - Removes fail-open dependency fallbacks.
  - Fails closed when POSIX locking, policy helpers, or native resource helpers are unavailable.
  - Treats active Catalog work, unresolved lifecycle receipts, and after-job runtime receipts (`Prepared`, `Deferred`, `Dispatching`, `Queued`, `Unknown`) as review blockers.
  - Keeps durable root receipts and before-images bound to actor, action, proof revision, review digest, and reviewed definition.

- `backend/lifecycle_executors.py`
  - Provides backend adapters implementing clone and retirement executor methods through `backend.lifecycle_target.invoke(...)`.
  - Reports extra readiness from real transport capability plus collector/store injection availability.

- `integration/lifecycle_resource_executor.py`
  - Applies clone candidates only when the reviewed resource set matches the canonical onboarding contract exactly.
  - Refuses shared/existing target resources, symlinks, traversal, non-canonical paths, copied history, copied secrets, and digest drift.
  - Resolves the existing storage secret only on the native host and never returns it to callers.
  - Captures opaque retirement before-images, deletes only the exact reviewed job file, and restores only canonical managed job paths.
  - Runs syntax and reload checks and returns `Unknown` when rollback cannot be confirmed.

## Safety model

- Clone remains disabled/manual after creation.
- Retirement preserves Pool, FileSet, Storage, Schedule, Catalog data, backup media, and retained recovery references.
- Readiness stays blocked unless the helper reports installed prerequisites, root access, and lock availability.
- Runtime coverage may still fail closed when unmanaged JobDefs or inbound hook coverage cannot be proven authoritatively.
- No live install, migration, timer activation, or production mutation was performed in this batch.

## Local verification

- `python -m py_compile backend/lifecycle_target.py backend/lifecycle_executors.py integration/apply_job_lifecycle.py integration/lifecycle_resource_executor.py backend/tests/test_lifecycle_executors.py`
- `python -m pytest --noconftest backend/tests/test_lifecycle_executors.py -q`

## Environment limitation

The full project pytest path currently pulls `backend/tests/conftest.py`, which imports `backend.auth` and then `backend.persistence`. In this workstation environment that chain fails before test execution because `python-dotenv` is unavailable. The owned executor tests were therefore verified with `--noconftest` so the result reflects only the isolated fixtures for this batch.
