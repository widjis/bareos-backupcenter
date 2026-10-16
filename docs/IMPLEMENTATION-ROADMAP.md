# Implementation Roadmap

Last updated: 2026-10-16 (UTC+08).

This is the canonical execution and progress tracker for Bareos Backup Center. Product scope lives in [PRODUCT.md](PRODUCT.md); architecture and behavioral decisions live in their dedicated documents. Evidence lives in [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md). This roadmap connects those sources to executable tasks.

## Current position

- Local dashboard, authentication/roles, application persistence, monitoring, scoped Run/Cancel and VMware inventory are implemented. Services remain loopback-only.
- PNET live onboarding, Full/Incremental, isolated VMDK restore and direct new-VM restore with an isolated OS-boot test have accepted evidence. Original PNET was preserved. Direct restore execution is root-scoped to the seven managed VMware jobs; only PNET has actual restore/boot acceptance. It and supports one disk-datastore mapping, no NIC, power off and Never overwrite.
- Restore progress polls current status/logs and explicitly delayed Catalog counters; a verified percentage/ETA is unavailable. Restore history uses exact journal-mapped VM destination names and distinguishes native warnings from explanatory classification.
- Verification is recorded per slice below and in IMPLEMENTATION-REPORT.md. The latest full backend checkpoint is 209 passed with one POSIX-only module skipped on Windows; later browser/live checks still have their own separate evidence and blockers. Do not interpret a single checkpoint as blanket release acceptance.
- Current focus: per-job scheduling code and isolated verification are implemented through interval, ordinal, dependency, retry and reviewed backup-window controls. Helper synchronization on the Bareos server and PNET-only live apply/scheduled-run acceptance remain separate gates before any broader rollout. Job lifecycle work follows after those gates. General policy application/provisioning expansion, multi-datastore mappings, guest-file/application verification, production deployment/hardening and other unchecked tasks remain open.
- The full application roadmap is not complete. Accepted restore/boot evidence is scoped to recorded test VMs and does not verify every guest file or application.

## Tracking rules

1. Read this document before beginning implementation. Select the relevant phase and task IDs.
2. Each task must be independently executable and have an observable completion result. Split vague work before starting it.
3. Task IDs are stable. Append new IDs rather than renumbering existing tasks. Phases do not need to be executed as a single uninterrupted batch.
4. `[x]` means the stated task is completed with appropriate evidence. `[ ]` means not completed. Annotate an unchecked task with `In progress` or `Blocked: reason` when applicable.
5. Code implementation, automated verification, live-service verification, and operator acceptance are separate tasks. Never substitute one for another.
6. Before ending an implementation session, update affected checkboxes, phase status, current focus, blockers, next tasks, and evidence pointers.
7. When scope or dependencies change, update the roadmap and relevant product/architecture/UX documents together. Record the reason in the change log.
8. Preserve unfinished tasks and explicit limitations. Never check a task merely because a related feature or scaffold exists.
9. Keep credentials, tokens, and secret values out of this document and its evidence references.
10. A planned task is not blanket authorization for external side effects. Follow the user's current authorized scope and preserve operational confirmation behavior.

## Phase summary

| Phase | Milestone | Status | Dependency |
|---|---|---|---|
| P00 | Project tracking | Complete | None |
| P01 | Environment discovery | Complete for the local baseline | P00 |
| P02 | Local monitoring and enterprise UI | Complete for the bounded monitoring scope | P01 |
| P03 | Application PostgreSQL persistence | Complete for the local persistence baseline | P02 |
| P04 | Confirmed Run/Cancel operations | Implemented; live-effect acceptance pending | P03 |
| P05 | VMware inventory browsing | Implemented; operator acceptance pending | P03; P04 implementation available |
| P06 | Recovery points and restore workflows | Inspection/export code implemented; helper integrated; live acceptance deferred | P03; verified restore capabilities; P05 identities for VM recovery |
| P07 | Policies, controlled provisioning, and Add to backup | Draft policies and dry-run apply implemented; live load pending | P05; P03/P04 persistence and operation patterns |
| P08 | Application identity and scoped permissions | Local accounts implemented; production authorization acceptance pending | P03; defined organizational access rules |
| P09 | Protection policies, alerts, and reports | Observed alerts/reports implemented; policy compliance and delivery pending | P05/P07 for inventory and policy coverage; P08 for scoped notifications |
| P10 | Operational hardening and release acceptance | Planned — production release gate | P04 live acceptance; P06/P07 acceptance for included features; P08 |
| P11 | Optional expansion | Deferred — scope selection required | Accepted baseline release and capability-specific prerequisites |

The roadmap splits the earlier product outline into implementation-sized milestones. Persistence is its own phase; read-only inventory is separated from provisioning so it can ship earlier. Restore and provisioning acceptance remain separate. Authentication gates remote/multi-user release, not the existing local monitoring work.

## Detailed implementation checklist

### P00 — Project tracking

**Status:** Complete.

**Goal:** Create a maintained execution tracker and link it to project instructions.

**Dependencies:** None.

- [x] **P00-001** — Create this roadmap with stable phase and task IDs.
- [x] **P00-002** — Record delivered scope separately from live-service acceptance.
- [x] **P00-003** — Add mandatory roadmap maintenance instructions to AGENTS.md.
- [x] **P00-004** — Link the roadmap from the documentation index and Product Brief.

**Evidence / exit boundary:** This document and [AGENTS.md](../AGENTS.md).

### P01 — Environment discovery

**Status:** Complete for the local baseline.

**Goal:** Establish verified integration capabilities without changing backup behavior.

**Dependencies:** P00.

- [x] **P01-001** — Read connection setting names without exposing credential values.
- [x] **P01-002** — Identify Bareos version, installation paths, operating system, and active services.
- [x] **P01-003** — Inspect Director binding, Catalog type, and console/profile ACLs.
- [x] **P01-004** — Inspect configured VMware Job and FileSet resources.
- [x] **P01-005** — Identify the shared File Daemon proxy separately from protected VM workloads.
- [x] **P01-006** — Inspect Storage, Pool, Volume, and schedule mappings.
- [x] **P01-007** — Confirm server UTC and convert operational display times to WITA.
- [x] **P01-008** — Locate the existing REST gateway and read its OpenAPI contract.
- [x] **P01-009** — Verify API authentication and remote HTTPS certificate trust.
- [x] **P01-010** — Verify read contracts for jobs, sessions, logs, FileSets, schedules, pools, and volumes.
- [x] **P01-011** — Inspect pre-job preparation and chain-retention source without executing cleanup.
- [x] **P01-012** — Record fixed six-VM allowlists as a future provisioning dependency.
- [x] **P01-013** — Document unsupported or unverified capabilities and preserve existing server configuration.

**Evidence / exit boundary:** [SERVER-DISCOVERY.md](SERVER-DISCOVERY.md), [OPERATIONS.md](OPERATIONS.md), and [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md).

### P02 — Local monitoring and enterprise UI

**Status:** Complete for the bounded monitoring scope.

**Goal:** Provide useful monitoring using real Bareos data with honest state semantics.

**Dependencies:** P01.

- [x] **P02-001** — Create the Next.js/TypeScript frontend and FastAPI backend scaffold.
- [x] **P02-002** — Keep API credentials and Director tokens in the backend.
- [x] **P02-003** — Implement fixed monitoring routes instead of a raw console/proxy interface.
- [x] **P02-004** — Normalize job definitions separately from JobId execution sessions.
- [x] **P02-005** — Extract configured VMware workload names and folders from FileSets.
- [x] **P02-006** — Keep configured workload identity separate from proxy/client identity.
- [x] **P02-007** — Normalize success, warning, failure, cancellation, waiting, and unknown states.
- [x] **P02-008** — Convert server timestamps with explicit UTC-to-Asia/Makassar handling.
- [x] **P02-009** — Retrieve a bounded recent-session window and document its limits.
- [x] **P02-010** — Create Overview metrics, protection timeline, exceptions, and activity summary.
- [x] **P02-011** — Create Jobs, Backups, Infrastructure, History, and Settings views.
- [x] **P02-012** — Implement shared table pagination and first-column name sorting.
- [x] **P02-013** — Preserve committed view, search, and page in URL state.
- [x] **P02-014** — Implement searchable session logs with backend secret redaction.
- [x] **P02-015** — Implement loading, empty, error, partial, and stale states.
- [x] **P02-016** — Apply the enterprise navy navigation rail and central visual tokens.
- [x] **P02-017** — Verify desktop/mobile layouts, keyboard operation, and dialog focus restoration.
- [x] **P02-018** — Run accessibility checks for the covered views and fix discovered contrast issues.
- [x] **P02-019** — Verify typecheck, formatting, production build, and browser workflows.
- [x] **P02-020** — Provide a local startup script and English development runbook.

**Evidence / exit boundary:** [DESIGN.md](DESIGN.md), [UX-CONTRACT.md](UX-CONTRACT.md), [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md), and the implementation report. Complete does not mean full Catalog browsing, RPO compliance, or vCenter discovery.

### P03 — Application PostgreSQL persistence

**Status:** Complete for the local persistence baseline.

**Goal:** Keep application state separate from Bareos and recover monitoring after restart.

**Dependencies:** P02.

- [x] **P03-001** — Confirm that POSTGRES_* settings are host SSH credentials.
- [x] **P03-002** — Inspect the PostgreSQL host/version and verify administrative access through SSH.
- [x] **P03-003** — Check that dedicated application database and role names are available.
- [x] **P03-004** — Create the backupcenter database without changing the Bareos Catalog.
- [x] **P03-005** — Create a restricted runtime role without superuser or role/database creation rights.
- [x] **P03-006** — Keep schema/table ownership with the administrator and grant explicit runtime rights.
- [x] **P03-007** — Create checksummed initial schema migration and migration marker table.
- [x] **P03-008** — Create connection, workload, session-observation, latest-snapshot, audit, and operation tables.
- [x] **P03-009** — Add scoped uniqueness and foreign-key constraints.
- [x] **P03-010** — Generate runtime credentials and append them to the local ignored .env.
- [x] **P03-011** — Retrieve the public PostgreSQL certificate over SSH and validate its chain at runtime.
- [x] **P03-012** — Persist normalized snapshots, workloads, and sessions in one transaction.
- [x] **P03-013** — Keep observed historical sessions separate from live recovery evidence.
- [x] **P03-014** — Restore the saved snapshot before live refresh after a new backend instance starts.
- [x] **P03-015** — Force live verification before considering a restored snapshot fresh.
- [x] **P03-016** — Show explicit persistence failure while allowing read-only monitoring to continue.
- [x] **P03-017** — Show database status, observation counts, and bounded collector audit history in Settings.
- [x] **P03-018** — Verify runtime cannot create schema objects or update/delete audit events.
- [x] **P03-019** — Verify migration rerun, real snapshot recovery, and credential isolation.

**Evidence / exit boundary:** [DATABASE.md](DATABASE.md) and the PostgreSQL section of the implementation report. Database backup/restore, retention automation, and hostname-verified production PKI belong to P10.

### P04 — Confirmed Run/Cancel operations

**Status:** Implemented; live-effect acceptance pending.

**Goal:** Dispatch only confirmed operations with durable state, audit, and conservative recovery.

**Dependencies:** P03.

- [x] **P04-001** — Inspect installed Run, Cancel, and single-session status response contracts.
- [x] **P04-002** — Verify the read-only job-filter contract used by active-session preflight.
- [x] **P04-003** — Define strict request DTOs for Run/Cancel and reject unrecognized overrides.
- [x] **P04-004** — Canonicalize cancellation JobIds and restrict safe job-name syntax.
- [x] **P04-005** — Require same-origin confirmation headers and explicit confirmation flags.
- [x] **P04-006** — Block unsupported mutations and prevent application framing.
- [x] **P04-007** — Validate enabled Backup job configuration before queueing and before dispatch.
- [x] **P04-008** — Reject Run when a fresh lookup finds an active session for that job.
- [x] **P04-009** — Validate cancellation against an active backup JobId.
- [x] **P04-010** — Serialize identical keys and action/targets with transactional advisory locks.
- [x] **P04-011** — Replay existing idempotency keys and block unresolved duplicate targets.
- [x] **P04-012** — Commit Prepared/Dispatching states and audit events before upstream mutations.
- [x] **P04-013** — Elect one dispatcher with a PostgreSQL session advisory lock.
- [x] **P04-014** — Record returned JobIds and reconcile accepted operations from Director status.
- [x] **P04-015** — Confirm cancellation only from the Director Canceled state.
- [x] **P04-016** — Treat timeout, HTTP 500, missing JobId, and interrupted dispatch as Unknown.
- [x] **P04-017** — Implement recovery of interrupted dispatch without automatic resend.
- [x] **P04-018** — Create Run/Cancel confirmation dialogs with Go back as default focus.
- [x] **P04-019** — Keep explicit browser retries on the same request key.
- [x] **P04-020** — Show persistent feedback and a bounded operation journal in History.
- [x] **P04-021** — Explain disabled actions and exclude Restore templates from Run controls.
- [x] **P04-022** — Verify simulated duplicate, timeout, database-failure, rejection, and cancel-race cases.
- [x] **P04-023** — Verify real PostgreSQL key uniqueness in a rolled-back transaction.
- [x] **P04-024** — Verify the real journal remained empty during implementation tests.
- [x] **P04-025** — Exercise process interruption during simulated dispatch and verify startup recovery end to end.
- [x] **P04-026** — Select an explicitly authorized noncritical job for live Run acceptance.
- [x] **P04-027** — Confirm live JobId acknowledgement, session tracking, and final outcome in the UI.
- [x] **P04-028** — Exercise cancellation only on an explicitly authorized active test session.
- [x] **P04-029** — Verify final cancellation and resulting backup/media state on the actual server.
- [ ] **P04-030** — Record operator acceptance and remaining operational limitations.

**Evidence / exit boundary:** [OPERATIONS.md](OPERATIONS.md), backend operation tests, browser operation tests, and the implementation report. Most recent recorded results: 19 backend tests and 7 browser tests passed; mutations were simulated. Live acceptance is not established.

### P05 — VMware inventory browsing

**Status:** Implemented; operator acceptance pending.

**Goal:** Browse real vCenter inventory without provisioning or guessing VM identity.

**Dependencies:** P03; P04 implementation available.

- [x] **P05-001** — Inspect the installed VMware plugin/VDDK version and supported inventory identifiers.
- [x] **P05-002** — Choose direct server-side vCenter access or a dedicated server-side inventory service.
- [x] **P05-003** — Verify vCenter endpoint, trust certificate, and read-only inventory permissions.
- [x] **P05-004** — Keep VMware credentials server-side and define connection secret references.
- [x] **P05-005** — Define inventory entities for connection, datacenter, folder, VM, and proxy mapping.
- [x] **P05-006** — Create an additive migration for inventory connection and VM identity records.
- [x] **P05-007** — Store connection-scoped VM UUID/MoRef identifiers independently of display names.
- [x] **P05-008** — Implement inventory session acquisition, expiry, and bounded reconnect handling.
- [x] **P05-009** — Read datacenters and folder hierarchy with stable parent references.
- [x] **P05-010** — Read paginated VM inventory and available power/host/cluster/disk metadata.
- [x] **P05-011** — Expose typed backend tree, VM-list, search, and synchronization routes.
- [x] **P05-012** — Persist inventory synchronization time and explicit source errors.
- [x] **P05-013** — Reconcile current six jobs with inventory identities; flag ambiguous matches.
- [x] **P05-014** — Distinguish discovered unassigned VMs, configured VMs, and backup evidence.
- [x] **P05-015** — Build Infrastructure -> VMware tree and searchable VM table.
- [x] **P05-016** — Implement explicit VM selection retained across search and pagination.
- [x] **P05-017** — Show a selected-VM summary and clear selection behavior.
- [x] **P05-018** — Test duplicate names, rename, folder move, removed VM, and limited permissions.
- [x] **P05-019** — Test authentication/TLS failure, stale inventory, empty inventory, and no search results.
- [x] **P05-021** — Verify actual read-only vCenter connection, fingerprint rejection, PostgreSQL recovery, and browser workflows; see INVENTORY.md.
- [ ] **P05-020** — Verify read-only browsing against the actual vCenter and record operator acceptance.

**Evidence / exit boundary:** Implementation: [INVENTORY.md](INVENTORY.md). Design: [VMWARE-ONBOARDING.md](VMWARE-ONBOARDING.md). P04 live acceptance does not block read-only inventory work. Add to backup remains disabled until P07 provisioning gates pass.

### P06 — Recovery points and restore workflows

**Status:** Inspection, gated export and approved helper/receipt integration delivered; live acceptance deferred.

**Goal:** Offer only restore modes the installed backend can support and verify.

**Dependencies:** P03; verified restore capabilities; P05 identities for VM recovery.

- [x] **P06-001** — Inspect BVFS and installed restore API/plugin capabilities.
- [x] **P06-002** — Distinguish ordinary file backup recovery from VMware disk/VM recovery.
- [x] **P06-003** — Document supported source/target combinations and unavailable restore modes.
- [x] **P06-004** — Define recovery-point identity and dependency-chain response DTOs.
- [x] **P06-005** — Resolve required Full/Differential/Incremental JobIds through verified APIs.
- [x] **P06-006** — Check metadata pruning, media availability, and missing chain members.
- [ ] **P06-007** — Implement bounded BVFS directory/file/version browsing for supported file backups.
- [x] **P06-008** — Expose supported VMware recovery items without implying guest-file browsing.
- [x] **P06-009** — Create durable restore-request schema extensions through a new migration.
- [x] **P06-010** — Extend typed operations only with validated supported restore parameters.
- [ ] **P06-011** — Implement source -> point -> content -> destination -> review wizard steps.
- [ ] **P06-012** — Validate target client, destination path, permissions, and explicit overwrite selection.
- [x] **P06-013** — Show required media and estimated work only when backed by available data.
- [ ] **P06-014** — Create scoped restore selections and expire/clean temporary selection state.
- [x] **P06-015** — Journal, dispatch, and reconcile restore JobIds without unsafe retries.
- [ ] **P06-016** — Test missing chain, unavailable media, pruned metadata, target mismatch, and timeout.
- [ ] **P06-017** — Test wizard back navigation, selection preservation, errors, and confirmations.
- [x] **P06-018** — Run a specifically authorized restore into an isolated test destination. PNET restore JobId 25 succeeded; server helper/native console acceptance only.
- [ ] **P06-019** — Verify restored file contents/checksums for file recovery.
- [x] **P06-020** — Verify VM/disk recovery and boot only where the selected plugin mode supports it.
- [x] **P06-021** — Record restore execution and content/boot verification as separate outcomes. JobId 25 execution and disk metadata reads passed; guest-data/boot acceptance remains open.

- [x] **P06-022** — Implement and simulate isolated whole-disk export review/confirmation, same-key dispatch and timeout/500 handling.
- [x] **P06-023** — Verify actual read-only chain/media/item and export-plan contracts.
- [x] **P06-024** — Prepare/test the local root target-helper review artifact without remote installation.
- [x] **P06-025** — Install/integrate the approved root helper and validate ownership, mode, receipt checks and disabled scope without executing it.
- [x] **P06-026** — Execute target preparation and verify actual destination permissions. Explicitly approved PNET isolated target prepared; Bareos write access and actual VMDK creation verified.

**Evidence / exit boundary:** [RECOVERY.md](RECOVERY.md) and [RESTORE-TARGET-PROPOSAL.md](RESTORE-TARGET-PROPOSAL.md). Export code is gated; no live restore or content verification occurred.

### P07 — Policies, controlled provisioning, and Add to backup

**Status:** Draft policy editing, durable rehearsal staging and syntax-verified previews implemented; live load/apply pending.

**Goal:** Turn selected VMs into reviewed Bareos configuration without bypassing gateway guards.

**Dependencies:** P05; P03/P04 persistence and operation patterns.

- [ ] **P07-001** — Define a policy model for scope, schedule, levels, repository, retention, and owner.
- [x] **P07-002** — Define repository/proxy/Storage/Pool mappings without equating resources to disks.
- [x] **P07-003** — Create additive policy, assignment, configuration revision, and provisioning tables.
- [x] **P07-004** — Define policy versioning and assignment conflict rules.
- [ ] **P07-005** — Choose a controlled provisioning service with explicit resource permissions.
- [x] **P07-006** — Define typed provisioning payloads and reject raw console/configuration input.
- [ ] **P07-007** — Generate Job/FileSet/Schedule/Pool/Storage changes only when required.
- [x] **P07-008** — Render the configuration diff and identify affected shared resources.
- [x] **P07-009** — Validate resource names, references, plugin identifiers, and Bareos syntax.
- [ ] **P07-010** — Recheck inventory identity and configuration revision immediately before apply.
- [ ] **P07-011** — Extend preparation/retention allowlists and mappings through reviewed provisioning. In progress: preview/apply now generate explicit prepare-vm-backup and chain-retention mapping proposals per generated job and persist them in the configuration revision; no server-side allowlist change or live validation is performed yet.
- [ ] **P07-012** — Implement coordinated apply/load/verification and per-VM operation outcomes.
- [ ] **P07-013** — Define compensation and manual recovery for partial apply without deleting backup history.
- [x] **P07-014** — Implement policy create/edit forms with owned validation and unsaved-change handling.
- [ ] **P07-015** — Implement Select VMs -> Policy -> Schedule/repository -> Review -> Apply wizard.
- [x] **P07-016** — Prevent duplicate assignment and duplicate submission across tabs/restarts.
- [ ] **P07-017** — Show Configured / Pending first backup after provisioning rather than Protected.
- [ ] **P07-018** — Offer first Run as a separate explicit action.
- [ ] **P07-019** — Test concurrent edits, rename/move, shared-resource impact, service failure, and reload failure.
- [x] **P07-020** — Provision an explicitly authorized test VM and verify resulting Director resources.
- [x] **P07-021** — Verify its first backup and recovery separately before accepting onboarding. PNET Full JobId 23 and explicitly approved Incremental JobId 24 succeeded on 2026-10-15; the engine resolved chain 23 → 24. New-VM restore JobId 27 and isolated OS boot accepted; guest-file/application verification is not claimed.

- [x] **P07-022** — Create/test revision-controlled draft policy persistence with no external job changes.
- [x] **P07-023** — Bind reviewed draft revisions to previews; reject existing/ambiguous assignment and storage/revision mismatch.
- [x] **P07-024** — Run actual Bareos syntax validation on private temporary disabled resources; verify no configuration applied.
- [x] **P07-025** — Define strict preview-only DTOs; reject raw configuration/console overrides.
- [x] **P07-027** — Reject noncanonical UUIDs, duplicate identities and empty/oversized preview selections in the generator.
- [x] **P07-026** — Generate new disabled Job/FileSet/Pool previews without physical Storage/device or schedule changes.

**Evidence / exit boundary:** [POLICIES-AND-PREVIEWS.md](POLICIES-AND-PREVIEWS.md), [VMWARE-ONBOARDING.md](VMWARE-ONBOARDING.md). Existing gateway configuration-write restrictions remain in place until an authorized controlled service is implemented.

### P08 — Application identity and scoped permissions

**Status:** Local accounts implemented; production authorization acceptance pending.

**Goal:** Replace the trusted local-operator boundary with server-enforced application identity.

**Dependencies:** P03; defined organizational access rules.

- [x] **P08-001** — Define roles and allowed operations/resources with the operator.
- [x] **P08-002** — Choose the intended identity provider and application authentication flow.
- [x] **P08-003** — Create identity, membership, role, and permission-reference migrations.
- [x] **P08-004** — Implement server-side login/session/logout handling.
- [x] **P08-005** — Implement session expiry and secure cookie/CSRF behavior for the selected auth model.
- [ ] **P08-006** — Map application permissions to restricted Bareos console/profile scopes.
- [x] **P08-007** — Apply scopes to snapshots, search, logs, inventory, audit, and operation reads.
- [x] **P08-008** — Authorize every mutation on the server and recheck before worker dispatch.
- [x] **P08-009** — Bind operation/audit actors to verified identities rather than local labels.
- [x] **P08-010** — Replace capability booleans with server-derived scoped action permissions.
- [x] **P08-011** — Create user/role Settings views and safe permission-change confirmation.
- [x] **P08-012** — Handle logout or permission change while a confirmation is open.
- [x] **P08-013** — Test direct-route access, cross-user IDs, cache scope, and queued permission revocation.
- [x] **P08-014** — Test session expiry, invalid identity-provider responses, and logout propagation.
- [ ] **P08-015** — Record authorization acceptance before binding any process beyond loopback.

**Evidence / exit boundary:** [AUTHENTICATION.md](AUTHENTICATION.md). Local sessions and role checks are implemented; per-resource/per-site scopes, separate Bareos ACL profiles and remote release acceptance remain open.

### P09 — Protection policies, alerts, and reports

**Status:** Observed alerts and reports implemented; policy-based compliance/delivery pending.

**Goal:** Report actionable protection evidence and notify only on meaningful changes.

**Dependencies:** P05/P07 for inventory and policy coverage; P08 for scoped notifications.

- [ ] **P09-001** — Define mandatory backup scopes and policy freshness targets.
- [ ] **P09-002** — Implement protection evaluation per workload/scope with known/unknown evidence.
- [x] **P09-003** — Keep backup freshness separate from restore-verification status.
- [ ] **P09-004** — Detect inventory VMs without assignments and policies without qualifying backups.
- [ ] **P09-005** — Create alert, acknowledgement, ownership, notification, and report-job migrations.
- [x] **P09-006** — Implement Open/Acknowledged/Resolved lifecycle with evidence links.
- [x] **P09-007** — Deduplicate related alert updates and define meaningful-change rules.
- [ ] **P09-008** — Implement maintenance windows and bounded escalation rules.
- [ ] **P09-009** — Define notification channels and server-side secret handling.
- [ ] **P09-010** — Implement notification retries without duplicate external delivery.
- [ ] **P09-011** — Build alert filters, ownership, acknowledgement, and activity history.
- [ ] **P09-012** — Build daily backup, policy compliance, capacity, and restore-test report queries.
- [x] **P09-013** — Implement scoped CSV export and print-friendly report views.
- [x] **P09-014** — Include period, timezone, source freshness, and scope on every report.
- [ ] **P09-015** — Test time boundaries, unknown data, acknowledgement semantics, and notification deduplication.
- [ ] **P09-016** — Validate selected real policy/report examples with the operator.

- [x] **P09-017** — Persist observed terminal failure/warning alerts with deduplication and later-success resolution.
- [x] **P09-018** — Verify actual PostgreSQL alert lifecycle in an isolated rolled-back namespace.
- [x] **P09-019** — Query observed backup history and neutralize CSV formula cells; show scope, timezone and coverage.
- [x] **P09-020** — Implement shared alert-state filtering, Admin acknowledgement and reviewer history; responsible-team ownership remains pending.

**Evidence / exit boundary:** [ALERTS-AND-REPORTS.md](ALERTS-AND-REPORTS.md). Durable session alerts are implemented; mandatory-scope/RPO evaluation and notification delivery are not.

### P10 — Operational hardening and release acceptance

**Status:** Planned — production release gate.

**Goal:** Make the chosen release recoverable, observable, secure, and accepted in its target environment.

**Dependencies:** P04 live acceptance; P06/P07 acceptance for included features; P08.

- [ ] **P10-001** — Choose deployment topology, service owners, target load, and release scope.
- [ ] **P10-002** — Define monitoring data, audit, operation, and inventory retention policies.
- [ ] **P10-003** — Implement administrator-owned retention without weakening append-only runtime privileges.
- [ ] **P10-004** — Create database backup/restore procedures and an isolated restore test.
- [ ] **P10-005** — Define recovery objectives and verify application recovery after database restore.
- [ ] **P10-006** — Replace development TLS assumptions with managed PKI and hostname verification.
- [ ] **P10-007** — Define secret rotation, certificate renewal, and credential-revocation runbooks.
- [ ] **P10-008** — Implement structured secret-safe logs, health/readiness, and worker-leadership metrics.
- [ ] **P10-009** — Measure Catalog/query cost, snapshot latency, queue delay, and inventory synchronization time.
- [ ] **P10-010** — Implement measured server pagination/filters where the bounded snapshots are insufficient.
- [ ] **P10-011** — Fault-test worker interruption, database restart, lost leadership, and Director outage.
- [ ] **P10-012** — Implement explicit operator reconciliation for Unknown requests without automatic resend.
- [ ] **P10-013** — Verify install/update/rollback procedures and migration compatibility.
- [ ] **P10-014** — Run the scoped browser/accessibility matrix across supported devices and browsers.
- [ ] **P10-015** — Document remaining unsupported features and evidence boundaries.
- [ ] **P10-016** — Obtain operator acceptance for every included live backup/restore/provisioning flow.
- [ ] **P10-017** — Deploy only the accepted release scope and verify actual hosted behavior.
- [ ] **P10-018** — Record release version, deployment evidence, rollback point, and operational handover.

**Evidence / exit boundary:** Local build/test success is not hosted deployment, recovery, or production acceptance.

### P11 — Optional expansion

**Status:** Deferred — scope selection required.

**Goal:** Expand only the capabilities the operator chooses after the core workflows are stable.

**Dependencies:** Accepted baseline release and capability-specific prerequisites.

- [ ] **P11-001** — Prioritize expansion items with the operator before implementation.
- [ ] **P11-002** — Design multiple Director/site connection scoping and aggregation.
- [ ] **P11-003** — Implement per-site permissions, worker leadership, and source freshness.
- [ ] **P11-004** — Integrate host/filesystem metrics for actual repository capacity.
- [ ] **P11-005** — Implement capacity trends/forecasts with explicit estimation labels.
- [ ] **P11-006** — Design folder/tag inclusion rules, exclusions, and membership-change previews.
- [ ] **P11-007** — Implement explicit automatic-enrollment and removal behavior without silent data deletion.
- [ ] **P11-008** — Add scheduled restore tests with supported verification hooks.
- [ ] **P11-009** — Verify database/application consistency for selected workload types.
- [ ] **P11-010** — Evaluate additional hypervisor/plugin integrations from verified installed capabilities.
- [ ] **P11-011** — Define scoped API/webhook integrations and their audit/delivery contracts.
- [ ] **P11-012** — Repeat live acceptance and operational runbooks for each enabled expansion.

**Evidence / exit boundary:** Instant VM recovery, guest application-item recovery, and immutable storage are not assumed capabilities. Research and verify before adding them to scope.

## Next work queue

1. Execute P07-035D on PNET only: run a reviewed live per-job scheduling apply plus scheduled-run acceptance while preserving the current production schedules for the other managed jobs.
2. Complete the requested job lifecycle in order: general edit P07-040, disable/maintenance P07-042, clone P07-041 and retirement P07-039. Preserve recovery history and current resource ownership constraints.
3. Implement and drill full backup-server recovery P10-019 before production acceptance, alongside existing application database recovery P10-004–005. Develop repository administration P07-043 and independent backup-copy P11-013 on their stated dependencies.
4. Add the upcoming calendar P09-018 and integrity checks P06-036; retain existing alert/notification, recovery-test, application-consistency and production deployment tasks.
5. Record live acceptance for each specifically selected backup/restore/configuration effect. Planning and isolated checks do not authorize destructive actions or select production policy values. Keep existing service scopes and active configuration unchanged until their reviewed actions are confirmed.

Earlier historical rollout notes are evidence of those slices, not a blanket current ban or authorization. Remaining unchecked acceptance tasks stay open; fixture, syntax and local UI success do not close live acceptance.

## Open decisions and constraints

| Item | Current position | Resolution task |
|---|---|---|
| Inventory integration path | Implemented direct backend pyVmomi connection with certificate pinning | Resolved: P05-002 |
| Stable VMware identity | Inventory UUID/MoRef identities verified; existing FileSet associations remain provisional candidates | P07 assignment reconciliation |
| Existing VM allowlists | Preparation and retention scripts explicitly name six VMs | P07-011 |
| Restore modes | Inspection and gated local disk-export code exist; helper deployment is verified; destination permissions and actual recovery are deferred | P06-026, P06-018 through P06-021 |
| Unknown operations | No automatic resend or force-unblock; missing JobId needs explicit reconciliation | P10-012 |
| Production identity | Local roles, actor claims, cache isolation and revocation verified; organizational acceptance/Bareos profile mapping pending | P08-006, P08-015 |
| PostgreSQL TLS | Certificate-chain validation is configured; hostname-verified production PKI is pending | P10-006 |
| Long-term storage | Observation/audit retention and database restore drills are pending | P10-002 through P10-005 |

## Change log

- 2026-10-14: Established the canonical roadmap and stable task IDs. Imported completed tasks from recorded implementation evidence while retaining unverified live effects as unchecked tasks. Split read-only inventory from controlled onboarding and added explicit authentication/production gates. Updated AGENTS.md, PRODUCT.md, and the documentation index to point to this tracker.

- 2026-10-14: Implemented direct read-only VMware inventory and verified 40 visible VMs; added additive migrations 002/003. Implemented operator-selected local accounts/roles through migration 004. Advanced P08 before destructive workflow expansion; preserved live acceptance and per-resource ACL work as open tasks.

- 2026-10-15: Added migration 005 isolated restore intent constraints, 006 draft policies and 007 observed session alerts. Verified worker process interruption and database-atomic actor denial. Implemented recovery inspection/export review, policy previews and observed reports/alerts while preserving all unverified live/provisioning/production tasks. Automatic review rejected the protected-server target helper; recorded a local review proposal and approval gate rather than bypassing it.

- 2026-10-15: Operator explicitly approved helper installation/receipt integration and deferred every live backup/restore/provisioning operation. Installed root-owned 0700 helper and receipt-only API validation; scope remains absent, helper unexecuted, and no receipt directory created. Split deployment evidence (P06-025) from destination permission acceptance (P06-026).

- 2026-10-15: Added migration 008 for configuration revisions and protected assignments, implemented typed `/api/provisioning/apply` dry-run staging, operation-journal rehearsal completion, and inventory overlays for prepared assignments. Kept live Bareos apply disabled; updated onboarding/UX/database docs and verification evidence.
- 2026-10-15: Extended provisioning preview/apply payloads with explicit preparation/retention script-review entries derived from current VMware workload jobs. Rehearsal revisions now persist reviewed allowlist proposals without modifying the original server scripts.

Run/Cancel activation now uses `BACKUPCENTER_OPERATION_DISPATCH_ENABLED=1` and an explicit six-job server-side scope. The earlier all-operation deferral has been superseded only for confirmed Run/Cancel. Restore also requires the independent restore dispatch flag and approved scope. VMware preview rejects noncanonical and duplicate VM identities and caps selection at 25.

## Windows startup verification — 2026-10-15

- [x] **P02-021** — Provide a Windows PowerShell local launcher, keep loopback/dispatch boundaries, fix the local CA path, and verify login plus an authenticated real-data snapshot. Evidence: IMPLEMENTATION-REPORT.md, Windows local startup section.
- [ ] **P02-022** — Obtain operator acceptance of the dashboard in the Windows browser. Local HTTP verification is complete; no production release or live-effect acceptance is implied.

## Current execution slice — scoped Run/Cancel activation (2026-10-15)

The operator requested continued implementation. This slice activates the existing confirmed Run/Cancel workflow for the six configured VMware jobs, adds server-enforced job scope, and verifies live effects using noncritical local acceptance jobs. Restore/provisioning and production release remain separate.

- [x] **P04-031** — Enforce an explicit operation-job scope on both Run and Cancel and expose it to the canonical action controls. Verified.
- [x] **P04-032** — Verify scoped controls through backend and browser tests.
- [x] **P04-033** — Activate six-VM controls after noncritical live Run/Cancel acceptance; keep restore and provisioning disabled.

- 2026-10-15: Scoped Run/Cancel implemented and activated. Local acceptance through the application produced JobId 18 T/OK and JobId 19 A/Canceled; original test configuration restored. Verified 28 backend/auth tests, four browser tests, TypeScript and live-data UI controls. Six-VM operator acceptance (P04-030), live restore and provisioning remain separate. Next implementation slice is policy application with reviewed preparation/retention and per-VM repository mappings.

## Controlled PNET onboarding pilot — 2026-10-15

The operator selected PNET (instance UUID 5208e076-eb89-9f06-2ef2-790ac92b4d71) for live Add-to-backup and first Full testing. Its initial power state is poweredOn; preserve it. The earlier RDS test selection is superseded and was never modified.

- [x] **P07-028** — Implement root-owned typed onboarding for explicitly approved VM UUIDs, with dedicated per-VM folder/device/pool and existing fixed schedule/retention guards.
- [x] **P07-029** — Wire reviewed live plans to the durable application journal and differentiate live apply from rehearsal in the canonical onboarding UI.
- [x] **P07-030** — Provision PNET through the dashboard flow, verify configured identity and first Full, and preserve its power state.

- 2026-10-15: Completed the UUID-scoped PNET live onboarding pilot and first Full through the actual browser workflow. Native dedicated folder/device/Pool/Job and fixed serial schedule are active; migration 008 is verified on the app database. Full JobId 23 succeeded in 77 seconds with zero errors; power preserved and snapshot cleaned. Applied an isolated Bareos 25.1.1 UUID-context compatibility patch with four checks. General provisioning/policy apply and restore remain unfinished. See VMWARE-ONBOARDING.md and IMPLEMENTATION-REPORT.md.

- 2026-10-15: Explicitly approved one additional PNET Incremental test through the application operations API. JobId 24 succeeded (10 seconds, 7,925,206 bytes, zero errors); native level I and engine-resolved chain 23 → 24 verified on PNET-0009. No VM power change, snapshots or consolidation requirement after completion. P07-021 remains open for actual recovery acceptance.

- 2026-10-15: Operator explicitly authorized PNET restore testing. P06-026 and P06-018 are in progress: latest recovery point 24 (Full 23 plus Incremental 24), one fresh UUID directory under the isolated restore root, Never overwrite. P06-020 boot acceptance remains separate. Use the installed server API/helper directly; dashboard restore transport remains unaccepted on Windows.

- 2026-10-15: PNET isolated restore JobId 25 succeeded in 106 seconds, zero errors, using Full 23 + Incremental 24. Read-only VMDK/GPT checks and ext signature passed; original VM state preserved. Fixed missing explicit FileSet (8 focused tests passed), installed with rollback. Native console API mode submitted the corrected command without an interactive prompt; reconciled without resending. P06-018/021/026 accepted; P06-019/020 and P07-021 remain open for guest-data/boot verification. Dashboard restore dispatch stays disabled. See RECOVERY.md.


## Direct VMware restore implementation — 2026-10-15

- [x] **P06-027** — Implement an Admin-only typed new-VM restore planning API that revalidates recovery evidence, fixes power off/network disconnected/Never overwrite, and reports UUID-source and target-verification blockers without dispatch.
- [x] **P06-028** — Add destination/review UI to RecoveryInspection with server validation, loading/error states and keyboard/browser acceptance.
- [x] **P06-029** — Resolve source UUID compatibility, discover/validate live vCenter target topology and permissions, and implement durable direct-VM dispatch before enabling execution.
- [x] **P06-030** — Independently accept new-VM creation, restored content and isolated boot through an explicitly reviewed destination.

Current slice: P06-027/028. No console restore command is used for preview, since API console mode can dispatch without a trailing yes. P06-029/030 remain follow-up implementation/acceptance gates.

- 2026-10-15: P06-027/028 implemented and verified: Admin-only typed review, source-chain/media revalidation, source UUID blockers, fixed off/disconnected/Never destination invariants, transient draft/discard guard and stale-response cancellation. 19 focused backend tests passed; five distinct recovery/browser tests passed across focused runs, including axe checks, invalid-field focus and 502 retry; final TypeScript passed. Actual PNET point 24 review returned [23,24], PNET-0009 and dispatchEnabled=false. P06-029/030 remain unchecked: live target discovery/validation, UUID-compatible new-VM execution and boot acceptance are not implemented.

- 2026-10-15: Operator requested completion, including isolated PNET new-VM acceptance. P06-029/030 now in progress. Implement root-scoped target discovery/preflight, receipt-gated UUID redirection with no NIC at VM creation, durable existing restore journal mode, post-restore verification and isolated boot. Preserve original PNET and avoid execution previews.

- 2026-10-15: P06-029/030 and P06-020/P07-021 accepted for the scoped PNET workflow. Actual dashboard restore JobId 27 created vm-32506 with zero NICs, zero errors and expected MAC/UUID regeneration warnings. Root receipt verified isolation and poweredOff; separate boot test reached running/guestToolsRunning and ended poweredOff. Original PNET remained on without snapshots. Current direct-VM workflow is complete within documented new-VM/single-datastore scope; no original-VM overwrite or application-data acceptance implied. See RECOVERY.md and IMPLEMENTATION-REPORT.md. Remaining P06 tasks concern separate file browsing/selection and guest-content features.


- [x] **P06-031** — Add read-only restore-session polling with current status, elapsed time, native Catalog counters, stage/log tail and explicit unknown percentage; verify active/terminal/error transitions without running another restore.

- 2026-10-15: P06-031 accepted. RestoreProgress polls the authenticated read-only session endpoint after each 3-second delay, pauses hidden tabs, aborts obsolete reads, stops terminal polling and preserves final/stale evidence. Dashboard tracks active restore sessions and session details expose the same panel. Three normalizer tests and two browser simulations passed; TypeScript passed. Live read-only JobId 27 verified Warning, 89 seconds, 16,044,756,500 bytes, 3 items, zero errors and log tail. No additional restore was executed. Precise active transfer percentage/total remains unavailable from the inspected installed status interface and is not invented.

- [x] **P06-032** — Remove the arbitrary source-name/-RESTORE prefix requirement while preserving existing VM, datastore-directory and destination reservation collision checks. Verify the operator-selected PNET-TEST2-RESTORE destination through read-only preflight.

- [x] **P06-033** — Explain observed native restore warnings and label restore history/drawers with the exact journal-mapped destination VM; keep unmapped native names and unrecognized warnings explicit. Verify without new restore execution.

- 2026-10-15: P06-033 verified. Exact restore JobId journal mappings label History/search/drawer with the destination VM while preserving the native job name. Progress explains explicit MAC/UUID regeneration warnings and keeps other warnings unclassified. Four backend tests, two browser tests and TypeScript passed. Read-only live JobIds 27/28 each showed zero errors and two identity-change warnings. No new restore or VM power action was issued.

- [x] **P04-034** — Add confirmed manual Full/Incremental selection with durable level-bound idempotency, typed native dispatch and preserved configured default; verify without a production backup run.

- [x] **P08-001A** — Implement confirmed existing-job schedule/Pool policy application with root receipts, source digest validation, no active jobs, syntax/rollback and retention-helper integration. Installation/preview and live policy-apply acceptance remain separate.

- [ ] **P08-001B** — Accept a specifically reviewed live policy Apply and its resulting Director/Catalog state. Not run: the operator has not selected/confirmed a policy change; current seven-job settings remain unchanged.
- 2026-10-15: P04-034 implemented and verified through typed native schema inspection, durable requestedLevel binding and simulated dispatch/browser tests. P08-001A now supplies scoped current/review/confirmed-apply/status APIs and Settings UI, root receipts, unknown-outcome blocking, file validation/rollback, per-Pool/Volume retention handling and post-apply verification. 117 backend tests passed (one POSIX-only module skipped), seven operation/policy browser tests passed and TypeScript passed. Isolated server fixtures verified writes/replay/rollback with console calls mocked; seven original plus three per-window retention fixtures passed. Actual Director parsed generated schedules in -t mode. Read-only seven-job preview and Catalog verifier query succeeded. No real policy Apply, backup, restore or cleanup ran. P08-001B remains open; later restore expansion/multi-datastore/server deployment work remains pending.
- 2026-10-15: Refined the Active backup schedule and retention dashboard form so editable fields hydrate from the current managed-policy response and Reset to current restores the live baseline instead of fixed defaults. TypeScript/build passed; added browser coverage for hydration/reset. Browser execution was blocked in this environment because the Playwright Chromium executable is not installed. No real policy Apply, backup, restore or cleanup ran.
- 2026-10-15: Fixed local Active policy Settings fallback so current/preview work on macOS when the Windows-only apply transport is unavailable. Verified 10 targeted backend tests, direct authenticated `200` responses for current/preview, and live browser interaction through login, baseline hydration, Reset to current, and preview review with no `502`. Apply remained disabled by server configuration; no real policy Apply, backup, restore or cleanup ran.

## Restore scope expansion — 2026-10-15

- [x] **P06-034A** — Extend the root direct-restore allowlist to all seven managed VMware jobs, retaining isolated new-VM constraints. Root-owned mode 0600 allowlist installed with rollback copy.
- [x] **P06-034B** — Read-only preflight each latest successful recovery point; record failures separately from restore execution.
- [ ] **P06-034C** — Actual restore and guest acceptance for the six additional VMs; requires a selected test destination and execution request.

## Settings navigation — 2026-10-16

- [x] **P02-035A** — Split Settings into URL-addressable Connections, Users, Permissions, Notifications, Audit and Policies subpages using existing navigation/draft guards.
- [x] **P02-035B** — Verify submenu isolation, reload, draft protection and responsive keyboard behavior.

## Per-job scheduling — 2026-10-16

- [x] **P07-035A** — Add a typed per-job calendar and deterministic native Schedule generation with separate Full cadence and recovery-chain volume reserve validation.
- [x] **P07-035B** — Add Jobs → Edit schedule using the existing reviewed policy owner, exact one-job scope, current-state hydration and draft guard.
- [x] **P07-035C** — Validate generated calendars with native Director syntax, read-only preview, isolated helper checks and automated verification without changing active jobs.
- [ ] **P07-035D** — Live operator-selected calendar apply and resulting scheduled-run acceptance.
- [x] **P07-035E** — Prepare the concrete helper synchronization package, hashes, ownership/modes, validation steps and rollback plan without deploying it.
- [x] **P07-035F** — Synchronize the Bareos server helper to the reviewed scheduling contract and confirm preview/apply compatibility before any live Apply.
- [x] **P07-036** — Periodic intervals and monthly ordinal-weekday schedules.
- [x] **P07-037** — After-job dependencies with cycle checking and restart-safe outcomes.
- [x] **P07-038** — Failure-specific retry plus reviewed interval/start-window controls without claiming a hard finish-time cutoff.

- 2026-10-16: P07-035A–C verified locally without changing the active seven-job schedule. `.venv\Scripts\python.exe -m pytest -q backend/tests` passed `125 passed, 1 skipped`; `python integration/check_calendar_policy.py` passed with native Bareos mutations mocked; `npm run typecheck` and `npm run build` passed. Read-only comparison against `10.60.10.77` confirmed that the deployed helper still uses the older contract and rejects fields such as `trigger_mode`, so helper synchronization remains separate from this local completion.
- 2026-10-16: P07-035E completed as documentation and packaging work only. `docs/SCHEDULING-HELPER-SYNC.md` now records the file set, SHA-256 baselines, required ownership/modes, backup procedure, syntax validation steps and rollback plan for synchronizing `/opt/bareos-api/active_policy_contract.py`, `/opt/bareos-api/apply_backup_policy.py` and the new `/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py`.
- 2026-10-16: Completed P07-036–038 in local code and reviewed UI/helper contracts. Per-job schedules now support hourly intervals inside reviewed window slots, ordinal monthly weekdays such as 4th Saturday, after-job dependencies with optional run-on-failure behavior and cycle rejection, plus retry count/delay controls backed by native Job directives. The backup-window contract was narrowed during audit: interval calendars use the end time to bound generated start slots, and after-job mode uses it only as an allowed-start gate. `Max Run Sched Time` was removed because it did not prove the UI's finish-time claim. Browser execution remains environment-blocked here until the Playwright browser binary is installed; live apply/scheduled-run acceptance remains P07-035D and server helper synchronization remains P07-035F.

## Job retirement and backup deletion — planned 2026-10-16

- [ ] **P07-039A** — Define separate Disable schedule, Delete job configuration (preserve backups by default), and Delete backup data actions. Inspect active jobs, after-job dependencies, shared resources, retained recovery chains and cleanup ownership before deletion. Preserve a managed retirement record so retained backups remain discoverable and restorable after the live job definition is removed.
- [ ] **P07-039B** — Implement Admin-only reviewed job-configuration removal with explicit confirmation, durable intent/audit, idempotency, Director syntax/reload verification and rollback. Do not remove shared Pool, Storage, FileSet or Schedule resources without separate verified ownership checks. Never delete backup data implicitly.
- [ ] **P07-039C** — Verify job-removal scope, unauthorized access, active-job/dependency rejection, interrupted delivery, rollback, retained-backup discovery and restore compatibility with automated and isolated helper/browser tests.
- [ ] **P07-039D** — Accept live removal of an explicitly selected disposable job while demonstrating that its retained backups remain available for recovery.
- [ ] **P06-035A** — Implement separately reviewed backup-data deletion with exact recovery-point/chain/media impact, retained-chain and shared-volume checks, explicit destructive confirmation and durable audit/reconciliation. Configuration removal must not imply authorization for data deletion.
- [ ] **P06-035B** — Test backup-data deletion in isolated fixtures and accept a specifically approved disposable backup dataset separately from job removal.

Dependencies: canonical confirmed-operation/authorization contracts and managed-resource ownership. Execution authorization is required for the specific deletion target; these unchecked tasks record implementation scope only. Existing scheduled chain-retention cleanup must be assessed so removing a job does not unexpectedly retire preserved backups or prevent deliberate later cleanup.

- 2026-10-16: Added explicit retirement/deletion tasks after the operator asked whether Delete job was tracked. No deletion implementation or live deletion was performed.

## Operational lifecycle gaps — planned 2026-10-16

The operator approved recording the eight gaps identified during the roadmap review. This expands planning scope only. Each group separates implementation, verification and live acceptance; all new tasks remain unchecked.

### General job editing — P07-040

Dependencies: reviewed provisioning/resource ownership P07-007, P07-010–013; versioned exact-job schedule editing P07-035; retirement identity preservation P07-039.

- [ ] **P07-040A** — Define stable job identity independent of display/native names, supported VM membership, descriptions and repository changes. Preserve the current one-VM-per-job engine mapping unless a separately verified multi-VM model is introduced; preview required Full baselines, resource changes and historical recovery impact before identity, FileSet or repository changes.
- [ ] **P07-040B** — Implement Jobs → Edit for supported names/descriptions, VM assignment and repository using revision checks, exact ownership, Admin authorization, reviewed apply, rollback and audit. Unsupported regrouping must be explicit, not simulated.
- [ ] **P07-040C** — Verify rename/move, old recovery-point lookup, shared resources, concurrent edits, active jobs and rollback in automated/isolated/browser checks.
- [ ] **P07-040D** — Accept changes to an explicitly selected disposable job and demonstrate recovery access to its old backups.

### Clone job — P07-041

Dependencies: controlled provisioning and P07-040 identity/resource contracts.

- [ ] **P07-041A** — Implement a reviewed clone draft with a unique name and explicitly selected VM, repository and schedule; do not duplicate secrets, history or shared-resource ownership. Keep automatic execution disabled until explicitly confirmed.
- [ ] **P07-041B** — Test name collisions, duplicate protection of one VM, resource isolation, authorization, interrupted apply and rollback.
- [ ] **P07-041C** — Accept creation of a selected disposable clone; first backup remains a separate confirmed action.

### Per-VM maintenance/exclusion — P07-042

Dependencies: job scope/assignment identity, P07-037 dependencies and P09-008 alert maintenance rules. This controls execution and is distinct from muting alerts.

- [ ] **P07-042A** — Define and implement temporary suspension/exclusion with reason, start/end/timezone and explicit resume behavior; retain configuration and backup history. Define handling of manual runs, active sessions, dependent jobs and missed runs without silently cancelling or replaying them.
- [ ] **P07-042B** — Test expiry, restart, clock boundaries, explicit resume, authorization, dependency behavior and accurate UI/audit state.
- [ ] **P07-042C** — Accept a chosen maintenance interval and resume on a disposable workload without deleting its backups.

### Repository administration — P07-043

Dependencies: resource ownership/provisioning, P08 permissions and P11-004 actual filesystem metrics.

- [ ] **P07-043A** — Define repository identities, paths, mount/storage ownership, supported SMB/local capabilities and secret handling; distinguish physical capacity, quotas and Bareos volume limits.
- [ ] **P07-043B** — Implement reviewed add/edit/disable, bounded write/read/delete probe in a dedicated temporary location, mount availability, capacity thresholds and disconnected/read-only state. Refuse live backup writes to a missing mount's underlying local directory. Keep repository removal separate from data deletion.
- [ ] **P07-043C** — Test access denial, full/quota-limited storage, disconnect/remount, credential failures, probe cleanup, shared-use impact and concurrent edits without exposing secrets.
- [ ] **P07-043D** — Accept one explicitly selected repository and its probe; backup migration and deletion require their own reviewed scope.

### Upcoming backup calendar — P09-018

Dependencies: P07-035–038 schedule/dependency/window semantics and current Director state.

- [ ] **P09-018A** — Implement timezone-explicit upcoming runs with job, expected level and schedule source; distinguish clock-triggered runs from after-job conditional starts. Show overlap/queue risk as an estimate, never promise actual runtime or infer missed-run replay.
- [ ] **P09-018B** — Test month lengths, weekday/ordinal rules, disabled/maintenance jobs, dependencies, stale configuration and day/time boundaries; compare supported cases with native Director schedule output.
- [ ] **P09-018C** — Accept selected real calendar examples and their observed scheduling behavior.

### Full backup-server disaster recovery — P10-019

Dependencies: P10-004–007 application database recovery/PKI/secrets, repository access and P08 authorization. Prioritize before production acceptance; application database backup alone is insufficient.

- [ ] **P10-019A** — Inventory Director/Catalog, Storage/File Daemon configuration, source-build/plugin/VDDK dependencies, certificates, encrypted secret recovery, helper receipts, allowlists, retention scripts/timers, mounts and application configuration. Define consistency, versioned manifests, off-server custody, recovery order and recovery objectives.
- [ ] **P10-019B** — Implement protected configuration/Catalog backup and documented recovery procedures with access controls and retention; do not expose credentials in ordinary exports/logs. Verify required dependency artifacts and licensing availability rather than assuming bundled redistributability.
- [ ] **P10-019C** — Perform an isolated clean-host restore drill including Catalog/media reconciliation, mounts, restored identities/permissions and duplicate-scheduler prevention; measure recovery and test a representative backup restore.
- [ ] **P10-019D** — Obtain operator acceptance of the disaster-recovery evidence, recovery objectives, custody and operational runbook.

### Independent backup copy — P11-013

Dependencies: P07-043 repository identity/access, complete-chain/media inspection and P10-019 recoverable metadata. Capability selection requires verified installed Bareos support before promising behavior.

- [ ] **P11-013A** — Evaluate native copy/migration or supported export mechanisms; define independent target, schedule, retention, encryption and failure-domain separation. Distinguish a copy from migration and filesystem duplication of live volumes.
- [ ] **P11-013B** — Implement reviewed copy policy and durable copy-session status with chain/dependency handling, bounded retries and target capacity/access checks; keep source data intact.
- [ ] **P11-013C** — Test partial copy, interrupted transfer, target outage, source cleanup, independent retention and Catalog/media discovery with isolated fixtures.
- [ ] **P11-013D** — Accept a selected copied backup by restoring from the secondary location without relying on the primary repository.

### Scheduled backup-integrity checks — P06-036

Dependencies: complete-chain/media availability, verified native read/verify capabilities, repository load controls and P09 notifications. Separate from guest boot/application recovery P11-008–009.

- [ ] **P06-036A** — Define supported verification depth: Catalog/chain availability, actual media readability and content checksums where available; make unsupported depth and last-check age explicit.
- [ ] **P06-036B** — Implement bounded scheduled/on-demand verification with durable results, load limits, pause/cancel semantics and alerts. Never label metadata-only checks as full data integrity or successful guest recovery.
- [ ] **P06-036C** — Test missing media, deliberate corruption in disposable fixtures, read errors, incomplete coverage, interruption and resource contention.
- [ ] **P06-036D** — Accept a selected real verification run and demonstrate detection of a controlled disposable fault without modifying production backups.

### Remaining decisions

Confirm the supported scope of multi-VM jobs before relaxing the existing per-VM architecture (P07-040A). Choose the secondary repository/failure domain (P11-013A), full-server backup custody and recovery targets (P10-019A), and supported integrity-check depth (P06-036A) during their design work. These unresolved details do not block the current documentation update.

- 2026-10-16: Recorded all eight operational gaps, mapped existing overlapping tasks as dependencies rather than replacing them, and refreshed the next work queue. Job lifecycle follows scheduling; full backup-server recovery is a production gate. No implementation, configuration change, external notification or destructive operation was performed.

## Coordinated acceleration — 2026-10-16

The operator explicitly authorized parallel TRAE delegation and requested GPT-5.4 for every delegated task. Three bounded tasks were submitted on the existing Bareos workspace with disjoint file ownership; the coordinator owns integration and canonical documentation. No production effects are delegated.

- [ ] **P07-044A** — Audit/fix scheduling execution, duplicate/restart/window/retry semantics and isolated helper tests. TRAE conversation a5737b4d7108458cb30f9f8677157b85; task b57776e8130949bdb9d7c0c4f39b24d4. In progress; no helper deployment or policy Apply.
- [x] **P02-036** — Make restore-progress browser fixtures deterministic and exercise current scheduling flows using installed Chrome. TRAE conversation db57757973a448e09e15c0adab3f0565; task f8f31871ba4546cf9904cb2d3ee5bccf. In progress; mutations intercepted.
- [x] **P07-044B** — Implement/test a pure lifecycle preview contract for disable, clone draft and config removal preserving backups. TRAE conversation 2e032a9cf8ea450fa45e8ec20db8164d; task 251992635b7b4067b0769d2790fb6605. In progress; no execution/API/UI activation.
- [ ] **P07-044C** — Coordinator verifies API/helper compatibility gates, reviews peer diffs and reruns integration/regression checks. Keep actual helper deployment and user-selected live policy acceptance separate.

Do not infer completion from accepted task creation or peer reports. Preserve existing uncommitted edits. Lifecycle preview does not deliver Delete/Clone execution. Production schedules, backups and data remain outside delegated mutation scope.

- [x] **P07-044D** — Coordinator implements and verifies a fail-closed API/UI helper compatibility gate. Eight isolated backend checks and two intercepted browser checks passed; live read-only current/preview confirmed old helper disables Apply while allowing an explicitly local-only review. This does not close peer execution-safety review or live helper deployment.

- 2026-10-16: Browser and lifecycle TRAE tasks completed; actual response model gpt-5.4 verified. Coordinator fixed the real empty-dependency-selector bug, corrected lifecycle serialization/fixtures and added fail-closed trusted-role/registry-coverage checks. Seven integrated browser tests and 145 backend tests passed (one POSIX-only skip). This accepts deterministic tests and a pure lifecycle preview contract, not live Clone/Delete or scheduling runtime deployment. P07-044A/C remain open while scheduling execution review continues.

## Interrupted scheduling rewrite recovery — 2026-10-16

P07-044A remains unchecked. TRAE conversation a5737b4d7108458cb30f9f8677157b85 is interrupted/canceled; it deleted integration/apply_backup_policy.py before delivering a replacement. The coordinator recovered the full pre-delete source from the task's captured file-read stdout, preserved a separate recovery copy under .local, and restored the working file without resetting to an older Git/server version. Python compilation and the isolated helper apply/dependency/replay/retry/rollback fixture passed with native mutations mocked. Git now reports Modified, not Deleted. No deployed helper, active job, schedule, backup data or production file was changed.

Before any further delegated rewrite, preserve a coordinator-owned pre-task source snapshot and require in-place/atomic replacement rather than delete-then-create. A replacement must compile before the old source can be displaced. Do not resume or resubmit the interrupted task without a new bounded scope and recovery snapshot.

## Acceleration batch 2 — 2026-10-16

- [x] **P07-045A** — Read-only bounded scheduling safety audit of the restored helper; no delegated source rewrite or deployment. Coordinator snapshot preserved under .local/delegation-snapshots/batch2-20261016.
- [x] **P07-045B** — Build/test a fail-closed read-only Disable preview evidence adapter, keeping missing identity/registry proof explicit.
- [x] **P10-020** — Draft a bounded backup-server disaster recovery inventory/runbook and acceptance checklist; no backup/export/restore execution.
- [x] **P07-045C** — Coordinator reviews the three results, integrates only verified preview capability, and runs relevant regression checks. Actual Disable, policy Apply, helper deployment and disaster-recovery acceptance remain separate.

All delegated tasks explicitly use gpt-5.4, disjoint new-file ownership, no delete-then-create, and no production effects. The previous interrupted task is not resumed blindly; context is carried into new bounded tasks because the current connector lacks follow-up support.

### Batch 2 reviewed results and next queue

All three TRAE tasks completed with observed model gpt-5.4. Conversations: audit 23019a0f434e4d3cabf784623c8c94c8; adapter df06af055d8241528f632d5badd04a37; recovery be87017ec83b45efa417a0d5d4ef8530. Coordinator accepted the bounded audit, pure adapter and draft runbook only. No API/UI execution was activated. Existing protected source hashes match the pre-task snapshot.

Coordinator tightened adapter evidence validation: missing operations/dependencies/intents cannot imply empty registries, malformed evidence produces blockers, and raw source errors are withheld. Full backend regression: 155 passed, 1 POSIX-only skipped. Recovery draft corrected to seven jobs; 953 words. Audit: 865 words.

- [x] **P07-046A** — Verify exact source-hook identity and uniqueness, including stale hooks on other jobs; add isolated negative fixtures.
- [x] **P07-046B** — Require positive queued JobId acknowledgement, then design persistent source-run/target deduplication and restart reconciliation; a lock alone does not solve replay.
- [x] **P07-046C** — Resolve before-window delivery with durable deferral or explicit unsupported rejection; preserve lossless after-job/retry read-back.
- [ ] **P07-046D** — Build authoritative stable-identity/resource/operations collectors before wiring Disable preview to HTTP/UI. Actual Disable execution remains separate.

Next implementation priority is P07-046A/B/C while live scheduling Apply stays blocked. Native helper deployment and real acceptance are not completed by offline mocks. P10-019 disaster-recovery acceptance remains open; the new runbook is a draft.

## Acceleration batch 3 — 2026-10-16

User authorized implementation of the agreed next queue. Protected source snapshot: .local/delegation-snapshots/batch3-20261016. Three GPT-5.4 tasks own disjoint new modules/tests: source-hook verification (P07-046A), durable trigger runtime (P07-046B/C), and conservative Disable evidence collection (P07-046D). Coordinator owns helper/API integration, regression and documentation. Native deployment and PNET acceptance follow only after reviewed offline checks.

### Batch 3 integration evidence and remaining gates

All three delegated results completed with actual response model gpt-5.4: hooks conversation 10bd47b8a96b4a1a9694b021d385ad71 / task 3be26861e6444b15818321b0b2d0ec29; runtime 276e0c42e6cf42aaa8ddd11f0eb4cdb3 / task 98d30c80f7be480586da543a96e51a93; collector a05ccd2d361f4abd8210bd58a3e7d0f2 / task 43bf8baccbbd48e69bdd20c355417ca3.

P07-046A/B close only their local source/test scope. Coordinator integrated exact unique hooks and retry drift checks in current/plan/verify, explicit source JobId, durable trigger generation, date expiry, successful native acknowledgement, terminal queued-job reconciliation and no automatic resend of ambiguous deliveries. Local snapshot fallback explicitly labels unverified fields. Schema compatibility alone no longer enables Apply; native execution readiness is separately required.

- [x] **P07-047** — Verify Admin-only read-only Disable review API/UI, missing-proof/error/retry/timeout/close states, mobile layout and regression. Execution remains unavailable.
- [ ] **P07-048** — Verify and install reviewed drain service/timer and helper companions in an isolated Linux environment; test native permissions, source JobId expansion, restart, missing Catalog rows and console acknowledgement. Prepared unit files are not activation evidence.
- [ ] **P07-049** — After native gates, conduct reviewed PNET-only scheduling Apply and scheduled-run acceptance before expanding to other jobs.

P07-046C remains open for native deferred-drain delivery acceptance. P07-046D remains open for authoritative stable-identity/resource/operation collectors; the current monitoring collector deliberately produces blockers, not fabricated proof. Actual Disable/Enable, Clone/Edit and configuration deletion remain subsequent lifecycle work.

- 2026-10-16 batch-3 acceptance: full backend checkpoint 190 passed / 1 POSIX-only skip; final collector role/API hardening 14 focused tests passed. Full browser suite 41 passed, including modal loading/cancel/error/retry/focus/390px/a11y. TypeScript and Next production build passed; git diff whitespace check passed. Isolated helper validates actual current/verify read-back, duplicate-hook/retry-drift rejection and rollback with native effects mocked. Local backend refreshed only after unresolved operation count was zero. Authenticated local preview returned HTTP 200 with executionSupported=false and explicit missing-proof blockers; current-policy read returned HTTP 200, Apply disabled. No production scheduling or backup data changed. Static premium audit reports only its known root DESIGN.md assumption; AGENTS.md explicitly requires canonical docs/DESIGN.md.

## Existing-conversation continuation — 2026-10-16

User explicitly requires reuse of existing TRAE conversations. Same-conversation follow-up has now been tested live on the hook conversation with gpt-5.4, unchanged hub/Desktop IDs and no tools. This supersedes earlier connector-limitation notes. No new conversations are authorized for this batch. Runtime conversation 276e0c42e6cf42aaa8ddd11f0eb4cdb3 continues isolated POSIX validation (P07-048); lifecycle conversation 2e032a9cf8ea450fa45e8ec20db8164d continues explicit authoritative-proof normalization (P07-046D/task7 dependency). Coordinator owns Linux validation and integration. Pre-task source snapshots are under .local/reuse-batch4/snapshot. Actual disable execution and production scheduling remain unaccepted.

### Existing-conversation results and nine-task status

Both follow-ups completed with observed gpt-5.4 and unchanged hub/Desktop chat IDs. New execution IDs are expected per follow-up and are not new conversations: runtime 34d1ff4c00084fee7cfc572e7d098e6a; lifecycle e625e108513c8e5f4d4eff3db52241f2. Protected existing source hashes remained unchanged. No additional conversation was created.

P07-046C now closes its local implementation/isolated-native scope: eight POSIX process scenarios include before-window Deferred -> Queued exactly once after opening and expiry on the next date. Native actual Bareos dispatch remains part of P07-049. P07-048 stays open for installed helper/real console, source JobId expansion and controlled PNET acceptance.

| Original task | Current state | Remaining acceptance |
|---|---|---|
| 1 Hook identity/uniqueness | Implemented and tested | Production helper activation under task 6 |
| 2 JobId/dedup/restart safety | Implemented; POSIX process tests pass | Actual console/source identity under task 6 |
| 3 Window/read-back | Implemented; isolated native deferral/drain tests pass | Actual scheduled PNET delivery under task 6 |
| 4 Disable preview | API/UI delivered | Actual execution belongs to task 7 |
| 5 Integration/regression | Current batch accepted, 206 backend passed / 1 skipped | Recheck after future changes |
| 6 Helper sync/PNET | Native preflight advanced; not deployed or accepted | Install/review exact candidate, source JobId/console proof, PNET scheduled run |
| 7 Disable/Enable | Not implemented; pure proof normalizer added | Authoritative collectors, durable execution, API/UI and native acceptance |
| 8 Clone/Edit | Not complete; preview contract only | End-to-end implementation and acceptance |
| 9 Remove job config | Not implemented; preview contract only | Retained-backup evidence, execution and acceptance |

Native evidence: four candidate configurations pass installed Bareos 25.1.1 Director -t; production config hashes unchanged. systemd static verification exits 0 with unrelated existing netplan/snapd warnings. Eight harness scenarios pass on Python 3.10 with actual fcntl and separate processes, fake SQL/console only. The same harness passes twice as bareos under a unique hardened transient timer, including timer restart; temporary units are stopped/cleaned and production drain units were not activated. Native scope and retained private-server evidence are in NATIVE-SCHEDULING-VALIDATION.md and .local/reuse-batch4/evidence.json. Full backend regression: 206 passed, 1 POSIX-only skip, existing AnyIO deprecation. UI unchanged; previous 41-browser checkpoint was not rerun.

## Task 6 helper synchronization and controlled PNET acceptance — 2026-10-16

User authorized continuation. Coordinator will preserve rollback copies, synchronize reviewed helper/runtime/unit candidates, verify native read-back and perform only a controlled PNET acceptance. Existing calendar cadence/time and all other VM job settings must stay intact. Broad Apply remains blocked pending explicit acceptance scope. Existing audit conversation is reused for a final read-only release review; no new conversation. Source snapshot and hashes: .local/helper-sync-20261016.

### Task 6 installed-helper and native PNET checkpoint — 2026-10-16

Reused audit conversation 23019a0f434e4d3cabf784623c8c94c8 (execution d6aab41157214342da159fa2a8747806, observed gpt-5.4), no new conversation. Seven helper/runtime/unit files synchronized with exact-source hashes, active-job/unresolved-receipt guards, atomic replacement and recovery copies. Latest rollback directory /root/backupcenter-helper-sync/20261016T070847Z-b2e70b1d. P07-035F closes helper synchronization/contract compatibility only.

Native temporary Admin source Job37 expanded source `%i` correctly and queued exactly one VMware-PNET Incremental Job38. Job38 completed T/0 errors, 25,151,998 bytes, six plugin files, 07:05:46–07:05:55 UTC. The Admin response parser did not confirm source acknowledgement; exact Catalog/receipt reconciliation confirmed Job37 without resubmission. Runtime replay returned Job38, with exactly one PNET run since preparation. Temporary source config removed and original config hashes verified before the separate policy Apply.

PNET-only policy Apply 5833207e-1c05-4cc1-b5b3-4f922631c584 is Applied, native read-back/replay verified. It creates BC-Policy-PNET while preserving Full 1/15, Incremental other days at 21:30 WITA, retention30/max6. All unselected configs unchanged. Coordinator fixed schedule-only plans to avoid unrelated shared retention-script migration; explicit retention-change fixture retains that reviewed migration. Shared retirement script stayed unchanged during acceptance.

P07-048 remains unchecked. Earlier in this batch, automatic approval review rejected persistent timer/service activation before explicit human approval existed; that rejection was not bypassed. After the human explicitly approved permanent activation, the coordinator rechecked the default runtime queue and the seven installed candidate hashes through the existing root wrapper, confirmed zero default receipts and 7/7 manifest hash matches, then ran `systemctl enable --now backupcenter-after-job-drain.timer` and `systemctl start backupcenter-after-job-drain.service`. Verified state: timer enabled/active with `SubState=waiting`, oneshot service `Result=success` and `ExecMainStatus=0`, `/var/lib/bareos-after-job-runtime` owned by `bareos:bareos` mode `0700`, Director/SD/FD active, zero default receipts, and one natural timer trigger observed at `Fri 2026-10-16 07:26:00 UTC` with next trigger `Fri 2026-10-16 07:27:00 UTC`. Keep P07-048 open until the remaining missing Catalog identity edge acceptance is verified. P07-049 remains unchecked for ordinary 21:30 clock-triggered acceptance; manual native handoff, installed drain activation and PNET-only Apply are accepted, but the normal scheduled run has not yet been observed.

Final local regression 209 passed, 1 skipped; helper fixture (including no unrelated retention migration and explicit-retention migration) passed; three helper-sync checksum/rollback fixtures passed. Authenticated local API current HTTP200, helperCompatible=true, general Apply=false, PNET schedule BC-Policy-PNET. See HELPER-SYNC-ACCEPTANCE.md and .local/helper-sync-20261016/evidence.json.

- Approved permanent drain activation was executed by TRAE through the existing scheduling conversation 23019a0f434e4d3cabf784623c8c94c8, execution 48b840368e1984c859b176b4fa85dcd8, observed gpt-5.4. Coordinator independently verified enabled/active/waiting timer, successful oneshot result, secure state directory, empty receipts and healthy Bareos services using read-only checks. No new conversation or backup was created. User preference: prioritize feasible implementation/verification through TRAE, reuse existing conversations, retain coordinator review.

## Lifecycle implementation batch 5 — 2026-10-16

The operator explicitly deferred task 1 (ordinary 21:30 scheduling acceptance) until tonight and authorized tasks 2–5: Disable/Enable, per-job Edit, Clone and configuration removal with backups preserved. Reuse existing TRAE conversations with GPT-5.4; no new conversations. Backend/native candidate ownership: 2e032a9cf8ea450fa45e8ec20db8164d (execution 7005fb2507fc9dc22a74da340868d7f9). Frontend/browser ownership: db57757973a448e09e15c0adab3f0565 (execution 4eadfa0745b141e2b024499fc1ee6588). Independent review: 23019a0f434e4d3cabf784623c8c94c8 (execution b9537732aa1a4cada8513f50bbf4d402). Coordinator owns integration review and canonical tracking. Snapshot: .local/lifecycle-batch5/snapshot.

- [ ] **P07-050A** — Implement authoritative lifecycle collection and reviewed Disable/Enable execution candidate, including automatic after-job/retry suppression, identity/revision validation, durable receipts and rollback; verify in isolation. Depends on P07-046D. Live activation/acceptance remains separate.
- [x] **P07-050B** — Integrate Jobs actions and review/result UI for Disable/Enable, existing per-job schedule editing, Clone and remove-configuration-preserve-backups; expose genuine readiness/blockers and unknown-delivery status.
- [ ] **P07-050C** — Verify backend/native fixtures, browser behavior, retained recovery discovery, auth, stale reviews, concurrency, shared resources and rollback; record implementation/deployment/acceptance separately.

P07-039A–C, P07-040A–C and P07-041A–B remain the existing scope owners for removal, general editing and clone work; append evidence without closing unsupported or unverified scope. No production job/configuration/data deletion, real backup/restore, broad Apply activation or clock-triggered acceptance is authorized by this implementation batch. No backup-data deletion UI is planned in this batch. P07-049 stays pending tonight.

### Batch 5 reviewed local checkpoint

P07-050B closes its local UI/API integration scope: Jobs exposes Disable/Enable, the existing exact-job Edit schedule, explicit Clone target fields and Delete config with preserved-backup copy, review/confirmation/receipt states, Unknown reopen protection and truthful blockers. It does not close production lifecycle execution. P07-050A/P07-046D and P07-050C remain open for authoritative registry/complete native proof and real deployment/acceptance. P07-039B–D, general-edit P07-040B–D and Clone P07-041A–C remain open where production adapters, source-policy cloning or acceptance are not delivered.

- [x] **P07-050D** — Verify the integrated local lifecycle candidates, Admin/same-origin API boundaries, strict request bodies, native candidate failure rejection, durable claim/no-resend tests, retirement preservation, worker outcome handling and browser review/result paths. Full backend 246 passed/1 skipped; initial full browser 42 passed/2 failed, followed by 11 targeted passes covering both corrected failures and new guards; TypeScript/build passed. See LIFECYCLE-LOCAL-ACCEPTANCE.md.
- [ ] **P07-050E** — Reconcile authoritative persisted managed identities for pre-existing live jobs, complete production Clone/retirement collectors/store/executors and native runtime coverage, then accept on explicitly selected disposable targets. Real reviews currently block: Clone/removal HTTP200 executionSupported=false; Disable/Enable HTTP409 missing persisted lifecycle identity. No real lifecycle mutation or backup/data deletion was performed. P07-049 remains deferred until tonight.

Existing conversations remained unchanged; latest reviewed execution IDs: backend hardening 653929258a6ce8134bb21fd1bf0645ba; frontend 4eadfa0745b141e2b024499fc1ee6588; Clone hardening 0645ae69d56b44a1abdba5cdab19fb40; retirement/router 14b0d615eecfa0019813915bcdde0cca. Actual response models were gpt-5.4. Coordinator integrated main router, outcome/root guards, request-key status, target fields and regression fixes. No new conversation. The local backend was refreshed only after unresolved operation count was zero. General policy current remains HTTP200/helperCompatible=true/Apply=false.

## Production lifecycle foundations batch 6 — 2026-10-16

The operator authorized the immediate priorities: authoritative existing-job/VM/repository registration and production collector/receipt/executor foundations. Ordinary21:30 scheduling acceptance remains deferred tonight. Existing GPT-5.4 TRAE conversations are reused with disjoint ownership: registry a05ccd2d361f4abd8210bd58a3e7d0f2 (execution bd32bacfd70dac8c4abeb145135c3a49), durable PostgreSQL store df06af055d8241528f632d5badd04a37 (27f8c3885c9c33d3caba6cc6ab31e182), native executor/transport 2e032a9cf8ea450fa45e8ec20db8164d (3e301cefeb8859c59829106cacedcec0). Coordinator owns existing application integration, reviewed additive migration/deployment and verification. Snapshot: .local/lifecycle-production-b6/snapshot.

- [x] **P07-051A** — Collect authenticated current Director/vCenter identity evidence and reconcile a distinct managed registry with exact job/VM/repository bindings, provenance, revision and conflict checks. Do not repurpose released staging assignments as live ownership.
- [x] **P07-051B** — Implement concrete connection-scoped PostgreSQL Clone/retirement receipt adapters with committed claims, actor/intent binding, target serialization, durable retirement references and read-back.
- [ ] **P07-051C** — Implement actual pinned Windows-to-native helper transport and root-owned native executor adapters; validate paths, before-images, runtime locks, capability evidence and Unknown/no-resend behavior.
- [ ] **P07-051D** — Integrate reviewed production foundations, apply only reviewed additive schema and identity metadata changes, verify read-only live collection and restart-safe receipts; keep unaccepted lifecycle mutations and broad Apply disabled.

No real Clone, job/config/data deletion, backup or restore is included in this foundations batch. Installation and actual state activation must be distinguished from source/fixture checks. Controlled PNET Disable/Enable acceptance remains a subsequent explicit stage after identity/runtime proof is ready. No automatic tonight monitor is requested.


### Batch 6 production metadata checkpoint

P07-051A and P07-051B are implemented and their reviewed additive schemas are applied. Current authenticated Director/vCenter collection resolved seven managed VMware jobs against 41 inventory VMs, accounting for 12 loaded Director jobs. Seven registry rows were inserted, then a fresh second reconciliation returned Replay with all revisions remaining 1. The old released Retired staging row was preserved. Migration ledger read-back verified exact checksums for 010/011. Six real PostgreSQL isolated acceptance checks passed: concurrent same-key claim, cross-connection key isolation, Unknown target claim retention, retirement duplicate rejection, retirement terminal CAS/isolation, and runtime receipt DELETE denial; the owned probe schema was removed. No Bareos dispatch occurred.

Coordinator integration adds a registry-backed Store composition and Admin-only sanitized registry/foundation status endpoints. Four composition/API tests and 23 registry/store tests pass. P07-051C/D remain open: native executor review and production collectors are still being completed. Initial broader regression has 269 passed, 5 failed, 1 skipped while the native transport task remains in progress; those failures must be resolved before acceptance. Ordinary21:30 acceptance remains pending. No native helper has been installed in batch 6 and no lifecycle mutation was requested.


### Batch 6 collector and local API integration checkpoint

The reused registry conversation completed production collectors (execution e0aedb8aa19efcf74b8fa9330febac39, GPT-5.4 requested). Seven collector tests passed, then actual read-only PNET collection confirmed same-VM Clone is blocked and retirement remains blocked without retention/cleanup ownership. The gateway now attaches production collectors and executor adapters, with fresh database readiness and the explicit lifecycle flag gating execution independently; method compatibility alone does not enable writes. Twenty-six focused integration tests passed. The refreshed local registry/foundations endpoints returned HTTP200 with seven entries, schema readiness true, native installed/apply false; policy current returned HTTP200/helperCompatible=true/Apply=false. A later full backend run reached285passed/1failed/1skipped; the remaining failure is the in-progress native Clone success fixture. P07-051C/D remain open pending native review, fixture correction and final application reload. No native helper deployment or lifecycle mutation occurred.


Final completed-component regression:286passed/1skipped, explicitly excluding the native executor fixture file still under hardening. Seven production collector tests and six real PostgreSQL acceptance checks pass. The final local backend reload includes collector wiring; authenticated registry/foundations return HTTP200/seven jobs, and removal review remains blocked. Native original execution completed and the SAME conversation received hardening execution97cd9db29047399ea32fb4875a5717e1, with concrete findings in LIFECYCLE-NATIVE-REVIEW.md. P07-051C/D stay open, including shared journal claim races, exact reviewed hashes, native before-image and rollback proof. No native package installed. No ordinary scheduled acceptance or lifecycle mutation performed.
