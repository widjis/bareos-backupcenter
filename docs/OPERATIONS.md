# Confirmed Run and Cancel Operations

## Release scope

Run an enabled backup job from Jobs, or cancel an active backup session from its detail drawer. The original Bareos server executes the operation using its current configuration. Restore, provisioning, configuration editing, and arbitrary console commands remain disabled.

This is a single local operator application bound to loopback. The actor label `local-operator` is not an authenticated enterprise identity. Remote hosting and multiple users require an application authentication/authorization design before enabling controls.

## User workflow

- Run now opens a confirmation naming the job and configured level. No request is queued until Run backup is selected.
- Cancel session opens a separate confirmation naming the JobId and explaining the incomplete-backup consequence. The default focus is Go back.
- Submission prevents repeated activation and preserves its idempotency key for an explicit retry after a browser transport failure.
- The operation is visible in History -> Operation journal and in a persistent feedback banner.
- Accepted is a request acknowledgement, not successful backup or confirmed cancellation. Director status supplies the final result.

## Backend boundary

Only POST `/api/operations` is enabled for mutations. It requires the local application Origin, a custom confirmation header, a UUID idempotency key, a supported kind/target, and an explicit confirmation flag. Unknown fields are rejected. This header/origin contract blocks cross-origin browser submission; it is not user authentication.

The backend revalidates the target against fresh Director data, and the worker revalidates immediately before sending. Run requires an enabled Backup job and no active session for that job in a fresh job-filtered Catalog read. This check cannot atomically prevent a concurrent request made outside Backup Center; Director concurrency settings remain authoritative. Because the installed API interpolates console arguments, this release supports job names containing only letters, numbers, dot, hyphen, and underscore. Cancel requires a positive canonical JobId for an active backup session. Only configured defaults are used; client, FileSet, Pool, level, storage, plugin arguments, and raw commands cannot be overridden from the browser.

PostgreSQL is required for mutation preparation and dispatch. If journal persistence fails, no new command is queued or sent. Read-only monitoring may continue with a durability warning.

## Journal and worker

```text
Prepared -> Dispatching -> Accepted -> Running -> Completed / Failed
                |
                +-> Unknown
```

Prepared intent and each state transition are committed with an audit event. Advisory transaction locks serialize matching idempotency keys and matching action/targets; unresolved requests block a fresh request for that target. A unique database constraint also scopes keys to the Bareos connection. Replaying a key returns its existing request and never creates a second command.

A PostgreSQL session advisory lock elects one worker for the connection. Prepared rows are processed only by the leader. Before any upstream mutation, the worker commits Dispatching. It never automatically retries a mutation. After restart or leadership recovery, interrupted Dispatching rows become Unknown rather than being sent again.

Run returns a JobId from the installed gateway. Cancel acknowledgement may have no terminal status; it is tracked using the original JobId. The worker polls the single-session endpoint. A cancel request completes only when the Director reports Canceled; a job that finishes first is reported as a failed cancellation. Backup warnings remain recorded as session outcome even when execution completed.

HTTP 4xx rejection is recorded as Failed. Timeout, connection loss after dispatch, HTTP 5xx, or missing JobId is treated as Unknown because the installed API can start a job and then fail to return its ID. Unknown without a known JobId cannot be automatically correlated: inspect Bareos history and arrange explicit operator reconciliation. There is no automatic resend or force-unblock control in this release.

The worker scans a bounded pending window; Unknown rows without a JobId remain visible in the journal but do not occupy the reconciliation scan. Operation/audit retention is not automated.

## Inspected existing server hooks

Read-only source inspection confirmed that prepare-vm-backup validates the CIFS mount and per-VM directory. Before a Full backup it changes used Append volumes for that VM to Used. The existing chain-retention timer runs at 13:20 UTC / 21:20 WITA and invokes a retention-respecting prune planner for eligible expired complete single-volume chains, preserving the latest successful Full chain in its plan.

These are existing server policies, not Backup Center changes. Run uses these hooks; it is not equivalent to bypassing preparation or retention. Script inspection is not operational proof of chain safety or recoverability. The preparation and retention scripts contain fixed allowlists of the current six VMs, which must be addressed during future VM provisioning.

## API routes

| Route | Purpose |
|---|---|
| POST /api/operations | Validate and persist confirmed Run/Cancel or gated isolated-restore intent |
| GET /api/operations | Latest 100 journal entries |
| GET /api/operations?key=UUID | Look up a request by idempotency key |
| GET /api/operations/UUID | Read one connection-scoped request |

No browser credential, Director token, or raw upstream error is returned in these responses. Application pages deny framing to reduce confirmation clickjacking risk.

## Verification boundary

Backend tests simulate job dispatch, duplicate requests, unsafe targets, finished sessions, database failure, HTTP 500, timeout, and cancellation races. Browser tests intercept every Run/Cancel submission and simulate acceptance or transport loss. The actual PostgreSQL uniqueness constraint was verified inside a rolled-back transaction. The real operation journal was checked empty before and after testing; no real backup or cancellation was initiated by implementation testing.

API source/contract and reads were inspected live. Successful live Run/Cancel side effects remain unverified until the operator explicitly chooses a job in the application. No exactly-once external execution guarantee is claimed.

## Latest isolated export and actor controls

RECOVERY.md defines the fixed isolated disk-export mode. Migration 005 stores and constrains destination/mode/overwrite. Export is Admin-only and remains disabled pending server scope/target-helper permissions and operator-selected test approval. Request/delivery retry behavior follows the same durable journal rules. Its simulated acceptance is not live restore proof.

Dispatching claims lock/read the verified actor row within the journal transaction, coordinating with role/disable edits. Worker interruption was verified with killed/restarted child processes, real PostgreSQL and mocked Director I/O in a separate connection namespace. Recovery produced Unknown and no resend; the original journal stayed empty. Account/session actions, draft policies and alert acknowledgement are separately typed metadata routes and do not dispatch Bareos commands.
