# Backup Center Implementation Report

Last updated: 2026-10-15 (Asia/Makassar). Historical phase sections retain their original evidence boundaries; the latest section supersedes earlier phase-specific unsupported-feature statements.

## Delivered

- Next.js 16.4.0 / React / TypeScript frontend with Overview, Jobs, Backups, Infrastructure, History, and Settings.
- FastAPI backend integrating with the existing Bareos REST gateway through fixed read-only routes.
- VMware workload extraction from FileSet plugin configuration, separate from the shared backup proxy.
- Protection timeline, bounded history, search and pagination, session details, and redacted session logs.
- Verified HTTPS certificate trust, server-side token acquisition, in-memory snapshots, partial-source errors, and stale-state retention.
- Locally bundled IBM Plex fonts, responsive layout, keyboard-accessible navigation and modal close/focus restoration.
- Local startup script, environment template without secrets, and development runbook.

## Live integration evidence

Remote HTTPS certificate validation and API authentication succeeded. Read-only Director version, jobs, FileSets, storage, schedules, pools, volumes, and session logs were tested.

The final live snapshot reported six configured VMware workloads, eleven job definitions, and seven Catalog sessions. Earlier Director history and the current Catalog may differ because Catalog data can be removed; missing evidence is labeled No backup recorded, not proof that a VM has never been backed up.

The user-edited `.env` was preserved during implementation. The backend uses only API connection settings. No configured password or secret value was found in the production browser JavaScript bundles or normalized snapshot response.

## Verification

- Backend tests: 7 passed (normalization, shared proxy identity, secret exclusion/redaction, warning status, UTC timestamps, restore-vs-backup evidence, origin/mutation boundary, and stale snapshot retention).
- Browser tests: 3 passed using an existing local Chromium executable. Live navigation, filtering and clear-search focus, session logs, dialog Escape/focus restoration, infrastructure, backups, mobile reflow, empty state, initial connection failure, stale refresh, URL search restoration, and reduced-motion mode were exercised.
- Automated accessibility scan of the Overview: zero violations for the selected WCAG tags. A warning badge contrast issue was corrected by lightening the semantic background while preserving the approved warning foreground.
- TypeScript typecheck, Prettier check, and production build passed.
- Design document lint: zero errors and zero warnings.
- Premium UI strict static audit: zero findings using a temporary symlink compatibility view. The auditor hardcodes a root DESIGN.md path; the compatibility view points to the maintained docs/DESIGN.md and the same project source without violating the docs-only policy. This audit does not establish runtime accessibility or production readiness.
- Desktop and mobile screenshots were visually inspected and are stored under ignored `.local/`.

## Current implementation boundary

The monitoring release now uses in-memory snapshots plus a dedicated PostgreSQL persistence layer. Persistent operation dispatch, worker reconciliation, SSE updates, and user authorization remain future components. The UI currently refreshes via bounded polling.

No backup, restore, cancellation, configuration write, service restart, or deployment was performed on the Bareos server during implementation. API token acquisition is the only upstream POST used by this release.

VMware inventory discovery, controlled provisioning, recovery-chain validation, restore execution, VM boot testing, policy compliance, filesystem telemetry, application-consistency verification, and multi-user access remain outside this release. Keep both application processes bound to loopback.

## Next phase

Review the monitoring experience with the operator. Inspect existing preparation/retention scripts and define identity, permissions, and response contracts before enabling operational writes or adding the VMware inventory/provisioning integrations.

## Enterprise view redesign

The operator requested a more enterprise-oriented monitoring interface. The redesign adds a navy navigation rail, compact environment header, shared metric strip, side-by-side timeline and exceptions, and a recent-activity summary beside the schedule. All existing views use the same typography, table density, status styling, and search toolbar.

DataTable now supports numeric-aware first-column name sorting with accessible header buttons and aria-sort. Navigation accessible names remain stable when count badges change. Overview activity shows four summary columns; the full History view retains the complete session columns. Narrow viewports stack panels and retain local table overflow.

Verification after final changes: production build and TypeScript passed; three browser tests passed including sorting, live session flow, accessibility scan, mobile reflow, empty/error/stale states; design lint had zero errors/warnings; strict premium static audit had zero findings using the documented compatibility view. Desktop Overview, desktop Jobs, and mobile Overview screenshots were inspected.

At the time of the visual redesign, no database was introduced. The subsequent persistence phase below adds PostgreSQL. Persistent policies, workload identity mappings, application users, audit history, and tracked operations will require the planned application PostgreSQL database, separate from the Bareos Catalog.

## PostgreSQL persistence phase

The supplied POSTGRES_* values were confirmed to be host SSH credentials, not database-role credentials. The host was inspected via SSH and PostgreSQL 14.22 was verified. A new dedicated backupcenter database and backupcenter_runtime role were provisioned; the Bareos Catalog and other application databases were not modified.

The runtime role has no superuser, database/role creation, schema creation, or audit update/delete privileges. TLS login with a pinned certificate and verify-ca was verified. Runtime settings were appended to the user-maintained .env without replacing its existing settings. Public certificate trust is stored in ignored .local/.

Normalized live snapshots, six workload mappings, and seven observed sessions were persisted. The initial migration was rerun successfully with checksum verification. A fresh adapter restored the real database snapshot during a simulated Bareos outage. A startup-cache freshness defect was found during restart verification and fixed; restored data now always attempts a live refresh regardless of the monotonic clock origin.

Settings now shows application database state, counts, and bounded collector audit history. Persistent observations are not merged into live recovery evidence. The operation_requests schema is reserved for future controls; no backup operations are dispatched in this release.

Final verification: 9 backend tests passed; 4 browser tests passed, including live database/audit UI and automated accessibility checks for Overview and Settings; production build and TypeScript passed; strict UI audit had zero findings. Snapshot and browser-bundle scans found no configured credential values. The finalized backend was restarted and connected to PostgreSQL successfully.

Database backup/restore, retention automation, authentication, operational controls, and VMware inventory/provisioning remain unimplemented. See DATABASE.md for the schema and limits.

## Confirmed Run/Cancel phase

Delivered Run now for enabled backup jobs, Cancel session for active backup sessions, canonical confirmation dialogs, persistent inline feedback, and a bounded operation journal in History. Restore templates are excluded from Run. Disabled states explain connectivity, active-session, disabled-job, and supported-name constraints.

The backend validates current Director configuration/session state, requires a confirmed same-origin typed request, commits journal state before side effects, elects a PostgreSQL worker leader, and reconciles accepted requests by JobId. Matching keys and unresolved action/targets are deduplicated. Mutations are never automatically retried; timeout, HTTP 500, missing JobId, and interrupted dispatch produce Unknown. A cancellation is complete only when the Director reports Canceled.

Read-only inspection of the installed API confirmed Run returns jobid, Cancel returns console acknowledgement, and single-job status returns a Catalog record. The job-filter GET-body contract was verified live without sending a mutation. Existing preparation and chain-retention scripts were inspected, including their fixed six-VM allowlists; those scripts were not changed or executed by this work.

Verification: 19 backend tests passed; the full seven-test browser suite passed, and the three operation browser tests were rerun after final UI refinements. Browser mutations were intercepted and simulated. Production build/TypeScript and strict UI audit passed. The actual PostgreSQL idempotency constraint was tested in a rolled-back transaction. The real operation journal remained empty; no job was started or canceled by implementation testing. The backend's worker leadership and final controls capability were verified using read-only checks. Credentials were absent from browser bundles and normalized responses.

Startup was initially rejected by automatic approval review because persisted Prepared requests could dispatch. A database check proved the journal empty; startup was then approved with that evidence. No workaround or queued test request was used.

Live Run/Cancel effects remain unverified until the local operator explicitly confirms an action in the UI. External exactly-once execution, application authentication, remote hosting, automatic resolution of Unknown without a JobId, restore, and VMware inventory/provisioning are not delivered in this phase.

## VMware inventory and local account phases — 2026-10-14

Implemented direct backend VMware inventory, fingerprint-verified HTTPS, scoped instance UUID/MoRef identities, additive migrations 002/003, 25-row server search/pagination, folder navigation and explicit selection. Real vCenter 8.0.3 reported 40 visible VMs. PostgreSQL persistence/reload and wrong-fingerprint rejection succeeded. Rename/move, duplicate-name ambiguity, missing UUID, replaced vCenter, stale/auth failure and secret-safe errors are tested. No VMware state or Bareos backup configuration changed.

The operator selected local accounts with Admin/Backup Operator/Viewer roles. Migration 004 adds hashed passwords and hashed durable sessions. Implemented login/logout/password change, confirmed account create/access changes, last-Admin protection, environment-wide read scopes, capability filtering and worker actor reauthorization. Initial generated login settings are stored in ignored owner-only local .env; values are not printed. Current recorded checks: 37 backend tests passed; 12 browser tests passed before the latest account-access/role-refresh refinements. Final verification is still in progress and must replace this qualifier only after rerunning.

Read-only recovery investigation confirmed the installed plugin's local-VMDK branch and existing-VM power-off/snapshot guards. The existing REST API does not expose BVFS or explicit dependency-chain endpoints. Director .bvfs_get_jobids read verification succeeded for completed JobId 17. No restore, backup, cancellation or provisioning was dispatched. Operator-selected live test targets are pending; restore execution and content verification remain separate requirements.

## Current implementation and acceptance — 2026-10-15

Delivered direct VMware browsing (40 visible VMs), local accounts/roles, database-atomic dispatch authorization, recovery chain/media/item inspection and gated isolated-export UI/code, draft policy revisioning and syntax-verified onboarding previews, durable observed session alerts, scoped history/CSV/print-page reports, and provisioning dry-run rehearsal staging. Migrations 002 through 008 are checksummed additive application-schema changes. User credentials are not printed; initial Admin login settings remain in ignored .env.

Recorded backend result: 71 tests passed. Browser checks use actual read-only metadata/report services and intercepted synthetic operation/account/policy/acknowledgement writes. A complete run passed 20 checks and exposed one ambiguous alert locator; the corrected alert and affected-flow reruns passed. The final complete-run/build status is recorded after its checks finish. Earlier 7/9/19/37-test sections are historical, not current totals.

Real PostgreSQL checks in rolled-back namespaces verified fixed restore intent/actor binding, atomic Viewer denial, draft revision conflicts and alert deduplication/acknowledgement/later-success resolution. A real killed child followed by a new worker recovered Dispatching to Unknown without resend using mocked Director I/O; its isolated fixture namespace was cleaned as administrator. No simulated queue entry was committed to the real Director namespace.

Generated disabled Job/FileSet/Pool resources passed actual bareos-dir -t as the bareos service user in a private temporary quoted include file. No resources were applied or Director reloaded. Read-only verification still found 11 jobs and no BC resources. The actual journal, draft-policy list and observed-alert list were empty after tests.

Server changes made before the approval block: additive typed recovery inspection and gated isolated-export modules on the existing REST gateway, with the configuration-write guard preserved and public readiness tested. No approval file or live restore/backend test-job setting was enabled. No backup, cancellation, restore or VM/config provisioning was dispatched.

Automatic review subsequently rejected root target-helper deployment because it changes protected server/API files and can prepare restore directories. The rejected command did not execute. A local-only tested helper/proposal was prepared; no indirect installation or execution was used. Explicit approval was subsequently granted for installation and receipt integration only; see the update below. The API user's NAS permissions remain unchanged and unaccepted for restore. See RESTORE-TARGET-PROPOSAL.md.

Full project completion is not claimed: controlled apply, preparation/retention mapping, assignments, live content/boot recovery, separate Bareos ACL profiles, policy RPO coverage, outbound notifications and production release gates remain open. All maintained documentation is English under docs/. Root AGENTS.md remains the instruction entry point.

### Final verified checks for this session

- Backend: 71 passed. Complete browser suite: 21 passed, including real read-only inventory/recovery/report reads, intercepted mutations, source failures, policy conflicts, keyboard/focus, accessibility and mobile coverage.
- TypeScript, production build and Prettier checks passed. Strict premium UI audit: zero findings. Python AST syntax and local documentation links passed.
- No configured password/JWT secret value appeared in production browser JavaScript. Original Director journal remained empty.
- At this earlier checkpoint root helper deployment was blocked; the approved installation update below supersedes this status. The API user's original share permissions were not broadened. Local services continue on 127.0.0.1:3000 and :8001.
- The static auditor briefly mistook useState<Form> for an HTML form. Actual forms already declared noValidate; the field type was renamed PolicyFields for clarity and the strict audit passed.

The roadmap currently records 150 completed tasks and 73 open tasks, including explicit live/provisioning/production/optional scope work. This is an accurate partial project milestone, not completion of every planned phase.


## Approved helper installation update — 2026-10-15

The operator authorized the named helper installation and receipt integration while explicitly deferring every live backup/restore/provisioning operation. Installed `/opt/bareos-api/prepare_restore_target.py` as root-owned mode 0700, replaced API-side share writes with descriptor-based root-owned receipt validation, and added one-shot backend preparation transport after the durable dispatch claim. Existing gateway configuration guards and API Unix groups remain unchanged.

Verification: 76 backend tests passed using `.venv/bin/python -m pytest -q backend/tests`, including disabled transport, canonical request identity and mismatched/writable receipt rejection. A direct `pytest` invocation initially failed import collection; module invocation resolved the runner path issue. Remote API readiness and root ownership/modes were verified. Restore scope is absent and receipt directory was not created. The real application operation journal is empty and local restore dispatch is disabled. No helper invocation, restore directory creation or backup/cancel/restore/provisioning dispatch occurred. Previous 21-test browser verification remains the latest UI evidence; this update changes backend/server integration only.

Installed source hashes are recorded after deployment verification in the session evidence. Destination permissions and actual restore content remain unverified; P06-026 and live acceptance remain open by operator instruction. The full roadmap is not complete.

Live-operation deferral is enforced by `BACKUPCENTER_OPERATION_DISPATCH_ENABLED=0`; server-side validation rejects every job mutation before remote preflight. Run/Cancel controls report monitoring-only state. Restore also requires the independent restore dispatch flag and approved scope. VMware preview rejects noncanonical and duplicate VM identities and caps selection at 25.

Final installed SHA-256 hashes (matched against remote files):

- `prepare_restore_target.py`: `e0ff83cbfe5759eeec9f80557ac0a7476d1660416980a172e6c6f28dd941ef69`.
- `backupcenter_restore.py`: `569325f9f37c2d462b9bf54758f095822ee2923b48025d345e4b13508cc3d8e8`.

Final verification after live-operation deferral: 76 backend tests and all 21 browser tests passed. Python syntax and local documentation links passed. Monitoring-only capabilities are server-enforced; the real operation journal remains empty.

## Controlled provisioning rehearsal update — 2026-10-15

Implemented migration 008 for `configuration_revisions` and `protection_assignments`, added typed `POST /api/provisioning/apply`, and extended the durable worker with a `provision` operation that stages Admin-reviewed dry-run onboarding only. Each accepted request revalidates fresh inventory/configuration, binds the selected policy revision, writes one configuration revision plus one prepared assignment per VM in a single transaction, and completes through temporary local fixture generation only. No Bareos configuration file was modified, loaded or reloaded.

Infrastructure now overlays staged VMs as `Prepared assignment` with `Pending controlled apply`, preventing duplicate onboarding selection across tabs/retries while remaining explicit that no first backup or live Director assignment exists. History renders these entries as onboarding rehearsals rather than backup/cancel operations.

The latest refinement adds explicit `scriptReview` payloads to preview/apply. These list the current VMware workload-job baseline and emit reviewed per-job additions for `prepare-vm-backup` and `chain-retention`, so the six-VM allowlist dependency is now captured in the configuration revision instead of remaining an undocumented manual blocker.

Verification for this update: `.venv/bin/python -m pytest -q backend/tests` passed with 82 tests. Targeted provisioning route/worker coverage included duplicate-selection blocking, typed apply staging, prepared-assignment overlay, script-review payload generation, and no-remote-I/O rehearsal completion. `npm run typecheck`, `npm run build`, `npm run format:check`, and Python syntax checks for changed files passed. Browser automation was not rerun for this slice; the previous 21-test browser run remains the latest UI evidence. The real Director journal remained empty and live provisioning stayed disabled.
