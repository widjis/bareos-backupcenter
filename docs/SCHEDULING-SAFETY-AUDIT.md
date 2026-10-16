# P07-045A Scheduling Safety Audit

## Scope

Read-only review of the restored scheduling helper and contract files:

- `integration/apply_backup_policy.py`
- `backend/active_policy.py`
- `integration/check_calendar_policy.py`
- `docs/SCHEDULING-HELPER-SYNC.md`

No source files, roadmap files, report files, services, or remote systems were changed.

## Actual Offline Evidence

- Read the current local sources and helper sync package document.
- Ran `python integration/check_calendar_policy.py` locally.
- Result: the isolated fixture passed for exact-job apply, after-job dependency wiring, replay, retry directives, custom-calendar rejection, and rollback.
- Limitation: that fixture mocks `console`, `active`, `syntax`, `fcntl`, `grp`, file roots, and all native mutations (`integration/check_calendar_policy.py:12-18,27-31,40-44,57-58`). It is useful regression coverage, but it is not evidence of native `bconsole`, Director reload, PostgreSQL, or restart behavior.

## Highest-Risk Defects

1. **After-job read-back does not prove source-hook identity or deduplication**
   - Location: `integration/apply_backup_policy.py::verify()` at `174-182`; weaker current-state check at `107-110`.
   - Failure scenario: a target job is marked `after_job` and its own `Schedule` is cleared, but the source job either has no `Run After Job` hook, has the wrong `--target/--level/--window-*`, or a stale hook remains on a second source job. `verify()` still marks the apply as `Applied`.
   - Evidence: the after-job branch only checks that runtime schedule is `None/''/'Manual'`; it never inspects the source job file or runtime trigger command. `current()` only checks for marker presence in one source file, not uniqueness.
   - Minimal fix: in `verify()`, read the selected source job config and assert exactly one managed dependency block for the target, with the expected command arguments and optional failure hook. Also assert no other managed job contains that target block.
   - Focused test: seed one correct source hook plus one stale duplicate on another job; require `apply()` or `verify()` to fail closed.

2. **Native `bconsole` acknowledgement is not validated**
   - Location: `integration/apply_backup_policy.py::trigger_script()->launch()` at `58-62`.
   - Failure scenario: `bconsole` exits with code `0` but rejects or does not queue the run command; the trigger script still reports success and the dependency chain silently stops.
   - Evidence: success is based only on `returncode == 0`. Stdout is not checked for a queued job acknowledgement or `JobId`.
   - Minimal fix: require a positive acknowledgement in stdout (for example a queued job message / `JobId`) or switch this helper path to the same reviewed native-console submission mode already used elsewhere.
   - Focused test: mock `subprocess.run()` to return `0` with stdout containing an error/prompt-only transcript and assert the hook raises.

3. **Concurrent or replayed hooks can double-launch the target**
   - Location: `integration/apply_backup_policy.py::trigger_script()` at `54-72`.
   - Failure scenario: two trigger invocations for the same target run close together (duplicate hook block, restart replay, manual rerun, or overlapping source completions). Both observe `active_target()==False` before the first queued job is visible in the catalog, so both call `launch()`.
   - Evidence: there is no per-target lock, receipt, or idempotency key around the active check plus launch sequence.
   - Minimal fix: take a per-target lock file before querying activity and launching, and keep it until acknowledgement is confirmed.
   - Focused test: run two concurrent hook invocations against a mocked `active_target()`/`launch()` sequence and assert only one launch occurs.

4. **After-job start-window semantics silently drop work before the window opens**
   - Location: `integration/apply_backup_policy.py::dependency_block()` at `32-37` and `trigger_script()` at `69-72`.
   - Failure scenario: source job finishes at `22:05`, target is configured for `time_wita=23:00` and `window_end_wita=23:30`. The hook exits `0` because it is outside the window, but nothing re-queues the target at `23:00`; the dependency is lost for that cycle.
   - Evidence: the helper performs a one-shot `in_window()` gate and then exits. There is no deferred receipt, retry-until-window-open loop, or alternate scheduler.
   - Minimal fix: either block live after-job windows until deferred-start behavior exists, or implement a durable pending-trigger record that is picked up when the start window opens.
   - Focused test: invoke the hook before `window-start`, then advance time into the window and prove whether a target launch is eventually produced. Current code will not.

5. **Runtime read-back in `backend.active_policy` collapses non-calendar state**
   - Location: `backend/active_policy.py::current_jobs()` at `129-153`.
   - Failure scenario: after a native after-job apply, a runtime snapshot is converted into UI/API state that always reports `triggerMode: calendar`, `afterJob: None`, `windowEndWita: None`, `retryCount: 0`, `retryIntervalMinutes: 30`. A later edit or review can silently lose the real dependency/retry configuration.
   - Evidence: `current_jobs()` never parses after-job hooks, retry directives, or managed schedule markers from the snapshot; it hardcodes the calendar/default values.
   - Minimal fix: either keep after-job/retry editing blocked when only runtime snapshot data is available, or extend read-back to parse the managed metadata needed for lossless round-tripping.
   - Focused test: feed a snapshot representing a manual/after-job-managed job and assert the returned row preserves trigger mode, after-job source, window, and retry directives.

## Recommendation by Feature

- **After-job hook identity/deduplication:** keep live Apply blocked.
- **Native `bconsole` acknowledgement:** keep live Apply blocked.
- **Concurrency/restart behavior:** keep live Apply blocked.
- **After-job start-window semantics:** keep live Apply blocked.
- **Apply/read-back/rollback evidence:** calendar/retry rollback remains mock-covered only; keep live Apply blocked until source-hook verification and lossless read-back exist.

## Bottom Line

The restored helper is locally consistent enough for offline fixture coverage, but it does not yet provide fail-closed proof for native after-job delivery. The current state is suitable for more targeted offline hardening work, not for native live Apply of after-job scheduling.
