# Implementation Roadmap

Last updated: 2026-10-15 (Asia/Makassar).

This is the canonical execution and progress tracker for Bareos Backup Center. Product scope lives in [PRODUCT.md](PRODUCT.md); architecture and behavioral decisions live in their dedicated documents. Evidence lives in [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md). This roadmap connects those sources to executable tasks.

## Current position

- Local dashboard, authentication/roles, application persistence, monitoring, scoped Run/Cancel and VMware inventory are implemented. Services remain loopback-only.
- PNET live onboarding, Full/Incremental, isolated VMDK restore and direct new-VM restore with an isolated OS-boot test have accepted evidence. Original PNET was preserved. Direct restore execution is root-scoped to VMware-PNET and supports one disk-datastore mapping, no NIC, power off and Never overwrite.
- Restore progress polls current status/logs and explicitly delayed Catalog counters; a verified percentage/ETA is unavailable. Restore history uses exact journal-mapped VM destination names and distinguishes native warnings from explanatory classification.
- Verification is recorded per slice below and in IMPLEMENTATION-REPORT.md. The latest full backend checkpoint is 100 passed with one POSIX-only module skipped on Windows; later focused changes have their own checks. Do not interpret an older full-suite checkpoint as a fresh full-release validation.
- Current focus: restore usability and operator-visible evidence. General policy application/provisioning expansion, multi-datastore mappings, guest-file/application verification, production deployment/hardening and other unchecked tasks remain open.
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

1. Implement the reviewed controlled provisioning service boundary and managed preparation/retention mappings behind the current durable rehearsal flow.
2. Preserve reviewed previews, staged assignments and existing configuration guards; keep live Bareos apply disabled until explicit operator approval.
3. Live Run/Cancel/export/provisioning acceptance is deferred by the operator; do not execute these operations or target preparation.
4. Finish Bareos ACL/profile mapping, accepted policy coverage/notification channels, production recovery/TLS/retention and deployment gates.

P04-026 through P04-030 and P06/P07 live acceptance remain open. Do not mark them complete from fixture, syntax or local UI checks.

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
