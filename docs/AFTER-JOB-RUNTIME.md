# After-Job Runtime

`integration/after_job_runtime.py` is a standalone local runtime for the future managed `Run After Job` hook. It does not modify the current helper integration by itself. Coordinator-owned integration work is still required before any live Apply.

## Scope

- Trigger command validates `--source`, `--source-job-id`, `--target`, `--level`, `--window-start`, and optional `--window-end`.
- `--source` and `--target` must match the managed VMware job pattern `^VMware-[A-Z0-9][A-Z0-9-]{0,63}$`.
- `--source-job-id` must be positive.
- Allowed levels: `configured`, `full`, `incremental`.
- All state is stored under an injectable state directory so offline tests can run without the live helper path.

## Durable behavior

The durable identity is `source + sourceJobId + target`, hashed into one receipt key. Each target also gets its own advisory lock file. The runtime writes an atomic, fsynced JSON receipt before any `bconsole` subprocess call.

Receipts use these states:

- `Deferred`: before window, target already active, or another unresolved receipt already owns the target.
- `Dispatching`: persisted before `bconsole` so a crash cannot silently resend.
- `Queued`: exactly one positive queued `JobId` was acknowledged.
- `Rejected`: transcript was explicit but unsafe, for example no `JobId`, multiple distinct `JobId` values, or obvious error text.
- `Expired`: the reviewed window closed before a deferred receipt could run.
- `Unknown`: subprocess delivery outcome was uncertain after `Dispatching`.

Existing `Dispatching`, `Queued`, `Rejected`, `Expired`, `Unknown`, or `Blocked` receipts are replayed as-is. The runtime never auto-resends them.

## Window handling

Before `window-start`, the trigger returns durable `Deferred` instead of silent success. Optional `window-end` is a start gate only; after it passes, deferred receipts become `Expired` without running. If the target is already active, the receipt also becomes `Deferred`.

`--drain` scans deferred receipts and retries them only when the window is open and the target is no longer blocked by activity or another unresolved receipt.

## Integration gate

This module intentionally ships without a daemon, timer, or deployment step. That means before-window deferred work will not run later unless another reviewed mechanism invokes `--drain`. The missing draining mechanism is therefore an explicit integration gate, not an accepted runtime guarantee.

## Offline evidence

Focused tests cover:

- strict validation
- durable before-window deferral
- expiry after window close
- active-target deferral
- rejected acknowledgement parsing
- crash after dispatch without resend
- per-target race/dedup with one dispatch

These tests are offline only. They do not prove live `bconsole`, PostgreSQL, or deployed helper behavior.

## Coordinator integration and hardening

The local helper now generates the installed trigger from this module, includes explicit source name and Bareos `%i` source JobId, verifies exact unique source hooks, and rejects retry drift. See [Bareos Director RunScript substitutions](https://docs.bareos.org/bareos-22/Configuration/Director.html) for `%i`; installed 25.1.1 expansion still needs native acceptance.

Coordinator added same-day expiry of deferred work, immutable replay intent, strict `Job queued` acknowledgement plus successful process exit, validated SQL counts, and terminal JobId/name reconciliation so a completed queued receipt does not block later source runs. Missing/ambiguous acknowledgement remains Unknown and is never resent. Dispatching/Unknown require operator reconciliation; no automatic resend is provided.

Prepared service/timer artifacts live in `integration/systemd/`; they are not installed or activated. Native `systemd-analyze verify`, user permissions, console access, Catalog status interpretation, timer restart and `%i` substitution are release gates. No Linux/systemd acceptance is claimed from Windows fixtures. Receipt storage is owned by bareos, directory mode 0700, files 0600.
