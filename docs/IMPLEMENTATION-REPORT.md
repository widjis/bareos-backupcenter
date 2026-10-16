# Backup Center Implementation Report

Last updated: 2026-10-16 (Asia/Makassar). Historical phase sections retain their original evidence boundaries; the latest section supersedes earlier phase-specific unsupported-feature statements.

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

## Windows local startup — 2026-10-15 (UTC+8)

Installed frontend dependencies using the existing npm lockfile and backend requirements in a project virtualenv, with Windows `tzdata`. Retrieved the existing PostgreSQL public certificate over an already trusted SSH host key and corrected only the stale macOS certificate path in `.env`. No database migration or bootstrap was required. Added `scripts/dev.ps1` for hidden, loopback-only Windows startup with local logs; it does not change dispatch flags.

Verified through the Next.js frontend: GET `/` 200, application login 200, authenticated GET `/api/snapshot` 200, Bareos connection connected, six configured VMware workloads, eleven job definitions, application database connected, and controls disabled. No backup/cancel/restore/provisioning dispatch was performed. Browser visual acceptance and production release acceptance remain separate; this update does not complete them.


## Scoped Run/Cancel activation — 2026-10-15 (UTC+8)

Added an explicit server-owned operation-job scope at queue and dispatch preflight. Cancel resolves the fresh JobId identity before authorizing scope. Gateway publishes the scope for the existing canonical Jobs and session-drawer controls; noneligible jobs stay disabled. Actual `.env` enables controls for the six canonical VMware jobs only. Restore/provisioning live dispatch was not enabled.

Real local acceptance through application login and POST `/api/operations`: InstallSmokeTest JobId 18 completed successfully (42 bytes, zero errors). A temporary 20-second pre-job delay on that same unscheduled local test job permitted an app-issued cancellation: JobId 19 became A/Canceled, zero bytes, zero errors. The original root-owned configuration was backed up, restored, validated and reloaded. The temporary test-job scope exception was removed; no VMware backup was manually dispatched. Durable operation records remain for traceability.

Verification: 28 targeted backend/auth tests passed; four Playwright operation tests passed; TypeScript no-emit check passed. Live-data browser verification confirmed a scoped VM Run button enabled, InstallSmokeTest disabled, and canonical confirmation focus/Go back behavior without dispatch. Screenshot: ignored `.local/scoped-controls-live.png`. Operator acceptance of the VM workflow, production deployment, policy application, provisioning and restore are not claimed.

## PNET live onboarding and first Full — 2026-10-15

Completed the actual browser workflow for PNET UUID 5208e076-eb89-9f06-2ef2-790ac92b4d71: select from VMware inventory, review dedicated resources, submit live Apply through the durable app journal, and perform a separate confirmed Run. Apply operation 6171964b-f027-4575-a5aa-d3267174702f completed. Migration 008 had not been applied on this checkout's app database despite earlier source documentation; it was applied additively as the existing PostgreSQL administrator, with no Bareos Catalog migration or credential reset.

Initial browser attempts stopped before submission; app journal and server resources/receipts were reconciled before a fresh attempt. No duplicate Apply occurred. Full trials 20/21/22 were terminal failures with zero bytes and were diagnosed before new requests; none was automatically resent on an ambiguous outcome. Findings and the UUID compatibility fix are documented in VMWARE-ONBOARDING.md.

Successful Full JobId 23: T, six files, 4,473,713,156 bytes, zero errors, 77 seconds, 12:16:12–12:17:29 UTC+8. Native volume PNET-0009 is 4,474,615,853 bytes. Final vCenter checks: poweredOn, CBT true, snapshot false, consolidationNeeded false. Scoped dashboard controls include the approved PNET job alongside the existing six. No root directory write-permission expansion was used. No global retention cleanup, second Incremental, VM power transition or restore was executed.

63 relevant backend tests and six browser tests passed; TypeScript checking passed. Four isolated UUID context checks passed locally and on the server. Broader live onboarding remains UUID-gated, policy editing remains draft-only, and recovery acceptance remains incomplete.


## Explicitly approved PNET Incremental acceptance — 2026-10-15

Following separate operator approval, submitted exactly one Run operation through the existing application API (operation f128f966-0108-4793-ac1f-21a431ad6f96), which completed as JobId 24. Native Catalog verified level I, status T, 7,925,206 bytes and zero errors. Execution was 14:36:58–14:37:08 UTC+8 (10 seconds). Read-only recovery inspection returned engineResolved=true, JobIds [23,24], Full and Incremental both on PNET-0009, with no Catalog blockers. VMware verification returned poweredOn, CBT enabled, no snapshots and consolidationNeeded=false. This supersedes earlier notes that the optional Incremental had not yet been authorized/executed. Actual restore, media readability and recovered data/boot acceptance remain untested. No product code changed and no additional backup or cleanup was submitted.


## PNET isolated restore acceptance — 2026-10-15

The operator explicitly authorized a restore test of PNET. Source recovery point 24 resolved Full 23 plus Incremental 24 on PNET-0009. The root helper prepared a fresh directory and Bareos write access was verified. A temporary root-owned scope contained only VMware-PNET and was removed immediately after the submission attempt; dashboard restore dispatch remains disabled.

The first API submission returned HTTP 500. Native history confirmed no restore job existed: the command omitted an explicit FileSet and Director reported “No FileSet found for client”. The corrected native console command included fileset=VMware-PNET and created exactly one restore, JobId 25. API console mode dispatched the valid command without an interactive confirmation, even without a trailing yes; future previews must not send restore commands in API mode. The root intent was reconciled to JobId 25 rather than resent. This run used the server helper/native console, not the dashboard restore workflow.

JobId 25 completed Restore OK, status T, zero errors, three restored stream items, 16,044,756,500 reported bytes, 2026-10-15 14:41:51–14:43:37 UTC+8 (106 seconds). Output: `/mnt/bareos-smb/backupcenter-restore-tests/81f30b01-5943-499d-bb9f-a22612632e63/[Local-MTIMRWESX01] PNET/PNET.vmdk`, corresponding to `F:\Backups\BareOSBackup\backupcenter-restore-tests\81f30b01-5943-499d-bb9f-a22612632e63\[Local-MTIMRWESX01] PNET\PNET.vmdk`. The standalone monolithicSparse VMDK is 15,201,140,736 bytes with virtual capacity 107,374,182,400 bytes (100 GiB). Only the VMDK artifact was emitted; three restored items do not mean three output files.

Read-only sparse-grain inspection validated the VMDK magic/descriptor, logical MBR signature, GPT header CRC, GPT partition-array CRC and ext filesystem signature in the 1 GiB partition. These checks establish basic disk-format/metadata readability, not guest-file equivalence, full filesystem integrity or boot/application recovery. PNET remained poweredOn, CBT enabled, no snapshots and no consolidation required. No test VM was registered or powered on. Retain the isolated VMDK for review; no cleanup was requested or performed.

The explicit FileSet fix was added to integration/backupcenter_restore.py, covered by the focused recovery regression suite (8 passed), and installed on the server with rollback copy /root/backupcenter_restore.py.before-explicit-fileset. Only bareos-restapi was restarted and is active. Actual recovery of guest data and isolated boot acceptance remain open; dashboard Windows SSH restore transport remains unaccepted.


## New VMware VM restore destination review — 2026-10-15

Implemented P06-027/028 only. backend/vm_restore.py owns a strict destination DTO and pure command-free review builder. POST /api/recovery/vmware/plan is Admin-only and same-origin, reuses recovery inspection and performs additional fixed GETs for source configuration. New-name/datacenter/host/datastore tokens and absolute folder paths are bounded/validated; power on, connected network, overwrite and extra fields are rejected. The review contains no secret-bearing plugin string or console command. Review digest covers intent, not approval or target attestation.

VMwareRestorePlan extends RecoveryInspection using canonical existing layout/fields and the shared draft/discard guard. Editing cancels pending review and invalidates the prior response; invalid fields receive focus, and errors preserve entries. No direct-VM execution button is exposed. Names remain manually entered and explicitly unverified. No VM creation, backup FileSet migration or additional restore was performed. Backend restarted locally to load the endpoint; original mutation flags were preserved.

Verification: 19 focused backend tests passed (test_vm_restore.py + test_recovery.py); existing recovery browser suite 3 passed; new VMware review suite 2 passed (including 422 focus and 502 retry). Browser execution requests are intercepted. TypeScript noEmit passed after final test changes. axe accessibility assertions passed for the reviewed desktop modal. Desktop and narrow screenshots were visually inspected; the modal scrolls at narrow widths. Live read-only PNET point 24 review resolved Full 23 + Incremental 24 and PNET-0009, detected UUID source addressing and returned dispatchEnabled=false.

Required strict premium audit ran with --no-write and found one tool limitation: it hardcodes root DESIGN.md and ignores the explicitly maintained docs/DESIGN.md equivalent documented in AGENTS.md. No root documentation duplicate was introduced. No other static findings were returned; this is not a clean strict-audit claim.

Open: P06-029 live vCenter target topology/capacity/permissions and name-collision checks; verified UUID compatibility for existing backups; disconnected-network enforcement and durable direct-VM dispatch; P06-030 independent guest-data/isolated-boot acceptance. Current slice is destination review, not end-to-end direct VMware restore.

## Current direct-VM restore status — 2026-10-15

The end-to-end new-VM restore workflow is implemented and accepted for the root-approved PNET source. Admin chooses live datacenter/folder/host/datastore, reviews current source-chain/target evidence, confirms a unique new VM name beginning with the source name plus -RESTORE, and monitors the existing durable operation journal. The new VM is created without any Ethernet adapters and stays powered off. Existing VM names and datastore directories are rejected; destination names are reserved across requests. Targets and required capacity (backed-up virtual disks plus reserve and memory) are rechecked before the durable one-shot command. Root scope is /opt/bareos-api/direct-vm-restore-scope.json, currently jobs=[VMware-PNET]; expansion is an explicit administrator action.

The opt-in compatibility patch reads a root-owned no-follow receipt, removes source UUID addressing only for that request, and redirects to the reviewed destination. Ordinary backup UUID handling is preserved. It rejects pre-existing targets and removes NICs before CreateVm. The gateway refuses execution if this patch is unavailable. Inputs never become arbitrary console commands; only validated source resource tokens and canonical IDs are composed. MAC/UUID regeneration is expected when the source VM still exists and may produce native Warning status.

Supported scope: new VM, one source disk-datastore mapping, Never overwrite, no NIC, powered off. Multi-datastore disk mapping, original-VM overwrite, arbitrary NIC reconnection, guest-file recovery, instant recovery and application-item recovery remain unsupported. Guest data/application validation is independent of OS-boot acceptance. Existing local VMDK export uses its independent flag/scope.

API: GET /api/recovery/vmware/targets; POST /api/recovery/vmware/plan; POST /api/recovery/vmware/restore with source_job_id, typed destination, review_digest, idempotency_key and confirmed=true; GET /api/operations/{id}; GET /api/recovery/vmware/result/{id}. Admin and existing same-origin protection apply. Submission digest/key bind source, destination and resolved target refs; changed reviews are rejected. Unknown delivery is never resent automatically. Root receipts live under /var/lib/bareos-vm-restore and preserve acceptance failures and successes.

Acceptance: dashboard operation 39f7035d-09fc-410a-9520-dbbeff537be4 / request 11c7b074-253a-41a9-9d89-c200c50b2733 created RestoreFiles JobId 27 from source 24 (chain 23 + 24). Native Restore OK -- with warnings, zero errors, three restored stream items, 16,044,756,500 bytes, 15:40:38–15:42:07 UTC+8 (89 seconds). Warnings concern generation of new MAC/UUID due to the still-existing original. VM PNET-RESTORE-TEST is vm-32506, instance UUID 5009413f-1183-85a8-1143-eb9d89cff648, host mtimrwesx01.mbma.com, datastore Local-MTIMRWESX01, folder /. Original PNET vm-29087 remained poweredOn with no snapshot; test VM has zero NICs and no snapshot.

A separately recorded isolated boot succeeded: guestState=running and guestToolsRunning, boot time 2026-10-15 07:43:29 UTC. The test VM was returned to poweredOff. Guest OS/name/disk telemetry was not populated in that observation window, so no guest-file checksum or application validation is claimed. Execution/isolation and boot proofs are returned separately by the result API and shown for recovery point 24 in the dashboard. Keep the restored test VM and earlier isolated VMDK for review; no deletion was requested.

Earlier JobId 26 failed before VM creation (zero bytes) because restore plugin options omitted config_file. Native history was reconciled and the failed receipt preserved. Added config_file=/etc/bareos/vmware-plugin.ini, then submitted a new separately reviewed request. No unknown request was retried.

Implementation evidence: migration 009 applied transactionally to the application database with checksum, pinned SSH and matching pre-existing TLS certificate; Bareos Catalog schema untouched. Real runtime transaction checks accepted the safe shape and rejected power/network/overwrite violations; all fixture rows rolled back. Backend suite checkpoint: 100 passed, 1 Linux-only POSIX module skipped on Windows; later focused recovery suite 25 passed including result API authorization. Recovery browser suite: 6 passed, including same-key uncertain delivery, invalid-field focus, inventory selects and axe checks. TypeScript passed. Actual live browser Apply/confirmation, VM creation, post-restore isolation, isolated OS boot, duplicate-target rejection, result API and dashboard evidence were independently verified. Screenshots: .local/direct-vm-restore-review.png, direct-vm-restore-confirm.png and direct-vm-restore-proof.png. Strict UI audit was run and still reports only its hardcoded root DESIGN.md mismatch; maintained docs/DESIGN.md is explicitly canonical in AGENTS.md. Do not claim a clean strict audit.

Deployment: /opt/bareos-api/direct_vm_restore.py and vm_restore_contract.py, root scope, and opt-in plugin patch. Plugin rollback copy: /root/bareos-fd-vmware.py.before-direct-restore. Disable BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED and restart local backend to stop new requests; preserve receipts/Unknown operations and resolve them before changing/removing resources. Roll back the plugin only with File Daemon idle. Reapply/revalidate the patch after a Bareos package/source upgrade. No additional network exposure was introduced.


## Observed restore progress — 2026-10-15

Implemented backend/session_progress.py and authenticated GET /api/sessions/{jobId}/progress, restricted to restore-type sessions and canonical positive bigint IDs. Reads the current Catalog row and bounded server-redacted log tail; no control/restore mutation is issued. Normalization distinguishes waiting, destination creation, disk restoration and terminal success/warning/failure/cancel states. Elapsed time derives from observed start/end time. Percentage and totalBytes are explicitly null because the installed source did not establish a reliable active total. Active Catalog counters can remain zero/unchanged until completion. An additional read-only native .status client=bareos-fd running probe returned no JSON counters; do not infer live throughput or percentage from backup compressed size.

RestoreProgress is mounted for active/submitted restore jobs and in the restore session drawer. Polling waits 3 seconds after a response, avoids overlaps, pauses hidden tabs, aborts stale/unmounted reads and stops on terminal status. Last received values remain labeled stale on errors; manual retry is read-only. The final result remains visible after the operation journal transitions out of Running. No duplicate top-level panel runs when a restore drawer is open. Latest logs are a collapsed, scrollable details section; no fake percentage/progress bar is displayed.

Verification: three backend normalization tests passed; two browser tests passed for active-to-warning terminal stop and stale-value recovery. Fixtures tolerate React development effect replay and do not submit operations. TypeScript passed. Actual completed JobId 27 returned phase Completed with warnings, 89 seconds, 16,044,756,500 bytes, 3 items, zero errors, null percentage and 24 log entries. Screenshot .local/restore-progress.png was visually inspected. No new backup, restore or boot was run. This is frequently refreshed observed status/log progress, not a verified live disk-byte percentage or ETA.


## Restore naming usability correction — 2026-10-15

Removed the agent-added name prefix restriction from the root direct-restore gateway and local source. No frontend/plugin change or service restart was needed. Exact operator destination PNET-TEST2-RESTORE, DC /Development, mtimrwesx02.mbma.com, MTIMRWME5024 passed live read-only preflight (Ready for confirmation, targetVerified=true, no blockers). Existing PNET name was independently rejected. All existing-name/directory/reservation and typed input checks remain. Root rollback copy: /root/direct_vm_restore.py.before-free-name. No new restore was submitted.


## Restore destination labels and warning explanation — 2026-10-15

History and session details resolve destination VM names only through exact restore JobId journal mappings. Unmapped native sessions retain RestoreFiles; the drawer preserves the native job name and search includes the mapped VM destination. Warning normalization scans server-redacted observed logs: explicit Warning entries mentioning an existing MAC/UUID and generated replacement receive identity-change explanation; other warnings remain unclassified and require review. Native Warning status is preserved. Original messages are expandable, and no application/boot guarantee follows from classification.

Verification: four backend progress tests passed, including unknown-warning preservation; two browser tests passed, explicitly opening both warning explanations, following the named history link and checking native-name provenance, as well as terminal polling/stale recovery. Final TypeScript passed. Actual read-only JobIds 27/28 both returned Warning, zero errors and two identity-change warnings. Local backend restarted with readiness verification; no backup/restore/boot was submitted. Screenshot .local/restore-progress.png inspected. Strict static UI audit again returned only the known hardcoded root DESIGN.md mismatch; docs/DESIGN.md remains canonical per AGENTS.md, so a clean strict audit is not claimed. Roadmap current-state prose was reconciled with accepted scoped restore evidence rather than leaving old deferrals presented as current.


## Manual backup levels and existing-job active policy workflow — 2026-10-15

Run now offers Configured default, Full and Incremental. Optional level is validated only for run requests, stored as requestedLevel, bound to the request key in API and transactional Store preparation, revalidated in dispatch and sent as the installed REST API jobControl.level. Default requests omit level and keep prior behavior. Selection is locked after a submission attempt so a retry cannot silently change intent. Confirmation initial focus is explicitly Go back; level edits do not reset focus. Requested level appears separately from actual native backup level, since Bareos may promote Incremental to Full. No real backup was started for this feature verification.

Settings now separates Active backup schedule and retention from existing draft policies. Admin chooses any subset of the seven managed jobs, reviews fixed Full dates 1/15 plus daily Incremental, start time after 21:00 WITA (UTC+08), retention >=30 days and a volume limit sufficient for the configured cadence/retention. Automatic mode may be disabled for manual-only operation. Existing job priorities, clients, FileSets, storage and preparation hooks are preserved. No policy change is submitted on page load or preview.

Root gateway /opt/bareos-api/apply_backup_policy.py accepts only typed current/preview/apply/status actions. Root-owned receipts under /var/lib/bareos-policy-applications bind canonical request ID, actor, desired definition and reviewed source/proposed-file digest. A shared retention lock and no-active-job preflight precede write/claim; unknown/Dispatching receipts block new requests. Atomic scoped file replacement, bareos-dir -t, reload, native Pool-default refresh and runtime Director/Catalog checks must succeed before Applied. Failure attempts to restore reviewed before-images and Pool defaults; unconfirmed rollback stays Unknown. Apply does not invoke backup/restore/prune/purge. The application serializes policy apply through its gateway lock and rechecks Admin role after acquisition.

Retention integration is installed only when an operator confirms Apply: the existing complete-chain planner uses max(Pool retention, individual Volume retention), preserving old volume minimums and latest successful Full protection. Pool defaults are refreshed; individual existing Volume minima are not shortened. The existing timer remains responsible for later retirement/recycling. Maximum volumes must be at least ceil(retention_days/14)+3 to accommodate scheduled chains and reserve; manual extra Full runs can require additional capacity. See the native volume-retention distinction in https://docs.bareos.org/TasksAndConcepts/VolumeManagement.html .

Configuration application receipts are a separate root-owned journal, not the backup/restore operation_requests state machine. UI reconciliation uses the same request ID, exposes it and does not resend on unknown delivery. Applied receipt resets the draft baseline and stale uncertainty; failed/unknown receipt messages remain explicit. BACKUPCENTER_POLICY_APPLY_ENABLED gates application and defaults to 0 in .env.example; local confirmed UI capability is enabled. No live Apply has been executed, so end-to-end Native policy-apply acceptance remains P08-001B.

Verification: complete backend checkpoint 117 passed/1 POSIX-only module skipped; focused active-policy/operation suite 26 passed; seven browser tests passed across operation/default/manual-level retry and policy unknown-status flows, with the final policy test also checking error clearance and navigation after reconciliation; TypeScript passed. Server temporary fixtures exercised real transforms/atomic writers/receipt replay/digest rejection/rollback with native console, active-job and initial verification boundaries mocked. Seven original retention safety checks and three Pool/Volume-window checks passed without Catalog I/O or cleanup. Actual bareos-dir -t parsed generated automatic/manual schedules through a temporary include file without reload. Native Catalog verifier query was exercised read-only against actual Pool values with schedule response mocked, including mismatch rejection. Read-only preview of all seven jobs reviewed 22 file entries; current 21:30 WITA/30 days/6 volumes settings remained unchanged. Strict UI audit still reports only the known root DESIGN.md/path-equivalent limitation; docs/DESIGN.md is canonical in AGENTS.md.


Final policy-helper fixture used the final verifier with simulated mutable Director/Pool responses: verified Apply and receipt replay passed; an injected post-apply Catalog mismatch caused rollback to the prior schedule and Pool defaults. Files/receipts were real only inside a fresh temporary tree. No production update/reload occurred. Settings capability copy now derives from role/configuration instead of stale “Restore not enabled / inventory not connected / single operator” literals. Final focused monitoring/policy/operation checks passed; policy panel spacing was aligned to existing tokens. The screenshot active-policy.png contains simulated Applied data and is browser-test evidence, not a real policy-application receipt.

Final live UI verification after backend publication rendered all seven managed jobs with no job selected; .local/active-policy-live.png was visually inspected. Active settings remained 21:30 WITA/30 days/6 volumes. Final focused monitoring/policy/operation suite: 35 passed. No Apply, backup, restore or purge was submitted.

The dashboard refinement now hydrates the editable Active backup schedule and retention form from the current managed-policy response and adds Reset to current so operators return to the live baseline instead of hidden defaults. This does not change the reviewed/apply transport or the existing request/receipt contract.

Verification for this refinement: `npm run typecheck` and `npm run build` passed after the UI update, and the touched files passed Prettier. Added browser coverage for current-value hydration and reset behavior in `tests/active-policy.spec.ts`. Browser execution could not run in this environment because the Playwright Chromium executable is not installed; frontend/backend local readiness was verified before that browser-launch failure. No live Apply, backup, restore or purge was submitted.

The active-policy current/preview routes now fall back locally when the Windows-only policy transport is unavailable, instead of surfacing a generic 502 in the Settings panel. This keeps live apply/status transport unchanged while restoring local Admin review of current schedule/retention values and preview generation. Targeted backend tests for the fallback passed (10 total in `test_active_policy.py`), and direct authenticated probes returned `200` for `/api/policies/active` and `/api/policies/active/preview`.

Browser-based verification against the live local app confirmed the intended operator flow: no `Active policy unavailable` error, six managed jobs listed, baseline `21:30 WITA / 30 days / 6 volumes`, Reset to current restored edited values and cleared the selected job, and Review active policy completed without a 502. Policy apply remained explicitly disabled by server configuration, as expected. No live Apply, backup, restore or purge was submitted.

## P06-034 — Managed VMware restore expansion, 2026-10-15

Expanded the root-owned direct-VM allowlist from PNET to all seven managed sources with a timestamped rollback copy and mode 0600. The fresh helper targets response contained exactly the seven intended jobs. All seven latest successful recovery points passed live read-only source-chain, metadata, target capacity, permissions and collision/reservation preflight on the destination documented in RECOVERY.md. The original MTIMRWZTNA01 name was correctly rejected. No dispatch, VM creation, power operation, backup configuration change or service restart occurred. Existing dynamic dashboard scope requires no frontend code change. Focused restore tests: 17 passed; one existing Starlette/anyio deprecation warning. P06-034C actual restore/guest acceptance remains open for the six additional VMs; PNET prior acceptance is preserved.

## P02-035 — Settings subpages, 2026-10-16

Replaced the combined Settings surface with six subordinate navigation destinations: Connections (default), Users, Permissions, Notifications, Audit and Policies. Each has a stable `view=settings&section=...` URL; invalid sections fall back to Connections. Existing account/active policy/draft policy controls retain their server authorization and shared form primitives. Permissions summarizes available capabilities; role assignment remains in Users. Notifications explicitly reports unavailable delivery instead of presenting a nonfunctional form. Audit requests are limited to its page and aborted on leaving. The shared discard dialog now retains the intended settings section and protects intra-Settings navigation. The navy sidebar uses its existing tokens and scrolls within short viewports; the mobile submenu scrolls horizontally.

Verification: TypeScript passed; production Next build passed (existing external package-lock warning); backend 119 passed, one POSIX-only skip, one existing anyio deprecation. New Chrome browser tests cover isolated subpages, direct-link reload, keyboard navigation, narrow viewport/overflow, axe accessibility and cancel/discard of edited policy state. Existing affected tests now open their relevant settings subpages. Initial accessibility checks found sidebar content overflow, which was fixed; a live monitoring test had a stale six-workload literal, replaced by its count-independent statement. Full browser rerun: 33 passed, one unrelated existing restore-progress fixture failed because its hardcoded JobId 27 history button was absent from the current paginated live history. Progress polling assertions passed before that missing-row click. All Settings, account, policy, monitoring, accessibility, draft-discard and submenu tests passed. Desktop/mobile screenshots were inspected at `.local/settings-submenu-desktop.png` and `.local/settings-submenu-mobile.png`. Changed-file formatting and git diff whitespace checks passed. No real policy/account write or Bareos configuration change was performed by these tests; mutation paths are intercepted.

Static premium audit retained at `.local/settings-navigation-audit.json`: one known path-assumption error because the tool checks root DESIGN.md while AGENTS mandates the maintained equivalent docs/DESIGN.md. Full formatting check reports 24 pre-existing untouched files; changed files were formatted. No unrelated formatting migration was performed.

## P07-035 to P07-038 — Per-job scheduling expansion, 2026-10-16

Expanded Jobs → Edit schedule for an exact approved Admin-managed job, still reusing ActivePolicySettings rather than introducing a second mutation owner. The editor now supports daily, selected weekdays, selected month dates, monthly ordinal weekdays such as 4th Saturday, hourly intervals inside a reviewed backup window, after-job start chains, run-on-failure behavior, retry count/delay, current-state hydration/reset, canonical dirty guard, human-readable review and confirmed one-shot apply/status handling. Time selection remains after 21:00 WITA as previously required.

The backend typed contract now distinguishes `calendar` and `after_job` trigger modes, validates monthly ordinal and interval inputs, enforces backup-window ordering, rejects self-reference and dependency cycles, and keeps per-job retention/volume reserve validation. The audit narrowed two behavioral claims before treating the slice as verified: after-job mode now requires Automatic schedule enabled, and backup-window end is accepted only for hourly interval calendars or as an after-job start gate. The root helper now reads/writes reviewed scheduling markers, installs a dedicated after-job trigger script, injects/removes dependency blocks, clears managed clock schedules for after-job mode, applies native retry directives, and verifies the loaded result according to the selected trigger mode. `Max Run Sched Time` was removed from the helper because it did not prove the UI's implied finish-time boundary. Existing legacy bulk policy editing continues to reject custom per-job calendars so reviewed one-job schedules are not silently flattened.

Read-only live comparison against `10.60.10.77` showed the deployed helper still running the older contract in `/opt/bareos-api/active_policy_contract.py` and `/opt/bareos-api/apply_backup_policy.py`. Preview requests that included `trigger_mode`, `after_job`, `window_end_wita`, `retry_count` or `retry_interval_minutes` were rejected remotely with `Extra inputs are not permitted`. The local API now falls back to the local preview generator for review-only preview when live Apply is not enabled, while still treating helper mismatch as a blocker for future live Apply. The remote helper also lacked the new trigger dependency script path `/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py`. No active job, schedule or Pool changed, no real policy Apply ran and no backup/cleanup was triggered.

Verification: `.venv\Scripts\python.exe -m pytest -q backend/tests` passed `125 passed, 1 skipped`; `.venv\Scripts\python.exe -m pytest -q backend/tests/test_active_policy.py` passed `16 passed`; `python integration/check_calendar_policy.py` passed and reported exact-job apply, after-job dependency, read-back, replay, retry-directive and rollback coverage with native mutations mocked; `npm run typecheck` passed; and `npm run build` passed with the existing external package-lock warning. A live Playwright scheduling run could not complete in this environment because the Playwright browser binary was missing, so browser verification is still limited to existing spec coverage in source plus earlier local evidence outside this blocked run. The concrete pre-deploy helper package, hashes, ownership/modes, validation steps and rollback plan are recorded in `docs/SCHEDULING-HELPER-SYNC.md`. Live helper synchronization and live apply plus scheduled-run acceptance remain separate tasks. Current production schedules were preserved during development.

## Retirement/deletion planning — 2026-10-16

A roadmap search found no explicit job-deletion task. Added P07-039A–D for job retirement/removal, preserved-backup recovery and independent acceptance, plus P06-035A–B for separately authorized backup-data deletion. Product scope now records the distinction. This update changes documentation only; no jobs, schedules, Catalog records or backup files were deleted.

## Operational gap planning update — 2026-10-16

Recorded all eight operator-approved planning gaps under stable IDs P07-040–043, P09-018, P10-019, P11-013 and P06-036. Each group has separate implementation, verification and live acceptance tasks, dependencies and an explicit capability boundary. Updated the next work queue and Product Brief; retained existing unfinished tasks and clarified that historical rollout notes are not current blanket authorization. This was a documentation-only update; all new tasks remain unchecked and no production state changed. Verification checked stable-ID uniqueness and presence of each new group in both roadmap and product scope.

## Coordinated TRAE acceleration and compatibility gate — 2026-10-16

The user authorized concurrent TRAE delegation. Three confirmed task receipts are recorded in the roadmap with manual gpt-5.4 selection and separate file ownership: scheduling execution audit, browser fixture stabilization and pure lifecycle preview contract. As of the latest bridge read, all three report in_progress but return only their initial user message; no assistant/model execution, changed files or completed result has been observed. Requested model selection is not presented as verified execution. No task was resent. Peer work remains unaccepted until actual diffs and tests can be reviewed.

The coordinator observed the local dev API/frontend stopped and relaunched them. Production Bareos Director/Storage/File Daemon remained active, seven latest Full jobs completed T with zero errors, SMB remained mounted with about 22 TiB free. No production schedules, data, retention flags or helper files were changed.

Implemented backend/policy_compatibility.py with API current/preview/apply integration: feature configuration alone cannot advertise live Apply for an older helper. Local-only previews expose unverified status and a concrete blocker. Apply rechecks helper compatibility before issuing any mutation. The shared ActivePolicySettings reflects the blocker and disables Apply on local-only review. Tests backend/tests/test_policy_compatibility.py cover malformed/old evidence, configured feature requirements, explicit local-only metadata and refusal to issue apply against legacy helpers; tests/policy-compatibility.spec.ts verifies disabled Apply for both initially enabled and disabled capability states, with writes intercepted.

Verification: 133 backend tests passed, one POSIX-only skip and existing anyio deprecation; both new browser tests passed; TypeScript passed. Authenticated live read-only current returned seven jobs, applyEnabled=false and helperCompatible=false. Preview returned 200 with Local preview only, applyEnabled=false and targetVerified=false. No live Apply was attempted. Static UI audit retained the known root-DESIGN.md path assumption, while docs/DESIGN.md remains canonical under AGENTS. Production Next build passed with the existing external package-lock warning. The peer review/deployment/actual scheduled-run gates remain open.


Acceleration integration update: browser and lifecycle peer responses now completed and both reported gpt-5.4. Coordinator review, corrections and evidence are in ACCELERATION-REVIEW.md and ACCELERATION-LIFECYCLE.md. The accepted checkpoint is 145 backend tests passed/one POSIX-only skip and seven integrated browser tests passed. After-job dependency options now use all available managed jobs while editable/Apply scope remains exactly the selected job. The former hardcoded live Job27 restore regression is replaced by deterministic intercepted data and its assertions pass. Lifecycle remains a pure contract without routes or mutation support. Scheduling helper rewrite is still pending and is not a deployment candidate.


Final accepted acceleration checkpoint: all 39 browser tests passed, including deterministic restore history/progress, scheduling, lifecycle-independent compatibility and existing operation/auth flows. All 145 backend tests passed with one POSIX-only skip. Final integrated TypeScript/Next build and changed-file formatting passed. The scheduling execution task remains in_progress with no final assistant result or candidate helper delivered at this checkpoint; its original local helper is temporarily absent during the rewrite, so no helper synchronization package is certified or deployed. The production helper remains intact and the running API explicitly blocks live Apply. This session does not certify pending peer changes that arrive after this checkpoint.


Recovery update: scheduling task a5737b4d7108458cb30f9f8677157b85 subsequently reported interrupted/canceled after delete_file. The coordinator restored integration/apply_backup_policy.py from its complete captured pre-delete file-read output, saved a separate .local recovery copy, and verified compilation plus integration/check_calendar_policy.py. The file is now present and Git reports Modified. This supersedes the earlier temporary-absence checkpoint. Runtime-safety audit remains incomplete and no server deployment occurred. Future delegated rewrites require pre-task snapshots and non-destructive replacement.

## Acceleration batch 2 — reviewed 2026-10-16

Three disjoint TRAE tasks completed, each with observed gpt-5.4. Delivered scheduling safety audit, pure Disable evidence adapter and backup-server recovery draft; see the documentation index. Coordinator hardened missing/malformed evidence handling and removed raw diagnostics from adapter output. Full offline backend regression: **155 passed, 1 skipped**, existing AnyIO deprecation warning. Protected pre-task source hashes unchanged. No source deletion, server mutation, backup/restore, helper deployment or policy Apply.

The audit identifies hook identity, native acknowledgement, replay/race, start-window delivery and lossy fallback read-back as remaining scheduling gates. Disable adapter has no API/UI/execution wiring. Recovery runbook is 953 words and explicitly unaccepted DR. Follow-up work P07-046A–D is recorded in the roadmap.

## Acceleration batch 3 — local integration accepted 2026-10-16

Three disjoint TRAE tasks completed with observed gpt-5.4; conversation/task identifiers are in the roadmap. Coordinator reviewed and hardened results, then integrated them locally.

- Helper validates exact unique source hooks, unmarked target commands, retry directives and policy markers. Plan rejects existing drift before preparing mutations. Source JobId `%i` is wired into generated hooks; installed version expansion remains unaccepted.
- Durable after-job runtime writes atomic receipts before dispatch, serializes each target, blocks uncertain replays, requires positive queued acknowledgement and a successful process exit, reconciles terminal queued JobIds by exact name, and expires old-date Deferred work. Drain service/timer artifacts are prepared only.
- Admin-only `/api/jobs/disable/preview` accepts only a scoped job name and forces a refreshed snapshot. Jobs provides Review disable with loading/error/retry/timeout/close states and no execution button. Missing authoritative identity/resource/registry proof remains explicit. Actual Disable/Enable, Clone and Delete are not delivered.
- Compatibility checks separate readable schema from native execution readiness. Live Apply stays blocked. Monitoring-only schedule fallback labels advanced fields unverified rather than presenting them as accepted read-back.

Verification: full backend checkpoint **190 passed, 1 skipped**; after final collector-role hardening **14 focused tests passed**. Full browser suite **41 passed**. Typecheck, Next production build and git diff whitespace checks passed. Existing external package-lock and AnyIO deprecation warnings remain. Isolated helper fixture passed with native mutations mocked, including real current/verify checks for duplicate hooks and retry drift. Mobile screenshot inspection found/fixed inherited nowrap clipping; final screenshot `.local/disable-preview-mobile.png`. Static premium strict audit reports one known path-assumption finding (root DESIGN.md); project AGENTS.md explicitly places maintained design context in docs/DESIGN.md. Audit evidence `.local/batch3-premium-audit.json`; no duplicated design document was created.

The local API was refreshed after confirming zero unresolved operations. Authenticated read-only local checks returned HTTP 200 for Disable preview (executionSupported=false, missing-proof blockers) and active policy (Apply disabled). No Bareos helper deployment, systemd activation, real policy Apply, backup/restore, data deletion or Git commit occurred. Next gates: isolated Linux/systemd/native acceptance, PNET-only scheduled-run acceptance, and authoritative lifecycle collectors.

## Existing-conversation continuation — 2026-10-16

Reused the runtime and lifecycle conversations with GPT-5.4; both completed, both hub/Desktop IDs preserved, zero new conversations. Runtime execution 34d1ff4c00084fee7cfc572e7d098e6a delivered the isolated POSIX harness; lifecycle execution e625e108513c8e5f4d4eff3db52241f2 delivered a pure proof normalizer. Coordinator reviewed/hardened both and added scoped native Director/systemd validation drivers.

Accepted evidence: **206 backend tests passed, 1 skipped**; eight real-process/fcntl Linux harness scenarios passed with fake dispatch only; four installed Director configuration-test candidates passed with production config hashes unchanged; static systemd check exited 0; a unique hardened transient timer executed the harness twice including timer restart. Temporary units cleaned; Director/SD/FD remained active. Protected existing source unchanged. No helper installation, production drain activation, actual policy Apply or backup dispatch. See NATIVE-SCHEDULING-VALIDATION.md for exact boundaries and private server evidence.

Proof normalizer rejects missing schedule ownership rather than fabricating resource rows, invalid/boolean revisions, stale dependencies/resources, malformed identities, repository mismatch and truncated coverage. It is not exposed as trusted HTTP input and does not implement Disable/Enable. Original task statuses and remaining task-6/task-7 gates are recorded in the roadmap.

## Installed helper and controlled PNET checkpoint — 2026-10-16

Helper synchronization completed with root recovery copies and exact manifest verification. Native PNET after-job handoff completed: Admin source37, PNET Incremental38, T/zero errors, 25,151,998 bytes, nine seconds. Source acknowledgement uncertainty reconciled without resend; receipt replay did not create a second backup; temporary fixture cleaned. PNET-only policy Apply 5833207e-1c05-4cc1-b5b3-4f922631c584 Applied/read-back/replay accepted, existing cadence/time/retention/max unchanged and unselected hashes intact. Schedule-only retention migration was removed and regression tested. Final backend 209 passed/one skipped. Local current API HTTP200, helper compatible, broad Apply still false.
Automatic approval review previously rejected persistent drain activation before explicit human approval existed; no bypass was attempted at that stage. After the human explicitly approved permanent activation, the coordinator rechecked the default runtime queue and seven installed candidate hashes through the existing root wrapper, confirmed zero default receipts and 7/7 manifest hash matches, then ran `systemctl enable --now backupcenter-after-job-drain.timer` plus `systemctl start backupcenter-after-job-drain.service`. Verified result: timer enabled and active/waiting, oneshot service `Result=success` with `ExecMainStatus=0`, `/var/lib/bareos-after-job-runtime` owned by `bareos:bareos` mode `0700`, Director/SD/FD active, and zero default receipts before and after activation. A natural timer trigger was observed at `Fri 2026-10-16 07:26:00 UTC`; next trigger was `Fri 2026-10-16 07:27:00 UTC`. This accepts installed drain activation only. Broad executionReady remains false, the remaining Catalog identity edge acceptance is still open, and ordinary 21:30 scheduled-run acceptance remains open. See `docs/HELPER-SYNC-ACCEPTANCE.md` and `.local/helper-sync-20261016/timer-activation.json`.


## 2026-10-16 lifecycle batch 5 local checkpoint

Implemented and reviewed local lifecycle backend/native candidates, Jobs review/confirmation/result UI, explicit Clone VM/repository targets and retirement preserving backup data. Reused existing GPT-5.4 TRAE conversations; no new conversation. Corrected fail-open dependency mocks, dispatch-before-durable-claim, helper/backend digest mismatch, worker false success and lost-response reconciliation gaps. Local backend refreshed after zero unresolved operation check.

Actual verification: 246 backend passed/1 skipped; initial full browser 42 passed/2 failed, both diagnosed and corrected; 11 targeted browser passes include those failures and new payload/blocker/Unknown guards. TypeScript/build passed; whitespace check passed. Strict UI audit retains its known canonical docs/DESIGN.md assumption; global format check flags 22 untouched older files. See LIFECYCLE-LOCAL-ACCEPTANCE.md for complete evidence and live blockers. Production lifecycle execution is not activated: authoritative existing-job identities and production collectors/durable adapters/executors/native acceptance remain open. General policy Apply=false; ordinary21:30 acceptance pending tonight. No new backup/restore/lifecycle/data-deletion operation.

Final local runtime: scoped frontend refresh after build resolved a transient identity proxy reset; final lifecycle keyboard/a11y/390px check passed (1 test). Touched-file formatting and final TypeScript/whitespace checks passed. Both loopback services remain available; no production lifecycle gate was opened.
