# Product Brief

## Goal

Help operators identify protected machines, address operational issues, monitor backup schedules, and restore files. Provide workflows familiar to Veeam users while retaining access to the underlying Bareos resource mappings.

## Navigation

- Overview: protection summaries, active sessions, and alerts.
- Jobs: backup definitions, policy assignments, schedules, and operational actions.
- Backups: backed-up workloads, recovery points, and restore entry points.
- Infrastructure: VMware inventory, backup proxies, repositories, and advanced media details.
- History: backup/restore sessions, logs, and reports.
- Settings uses separate subpages, rather than one combined settings page:
  - Connections: Director connection and application database status (default).
  - Users: local account creation and account access editing.
  - Permissions: existing role boundaries and available capabilities; role assignment is managed under Users.
  - Notifications: delivery availability; configuration remains unavailable until implemented.
  - Audit: collector and application audit events.
  - Policies: active schedule/retention and draft backup policies.

Job configuration and available backups are separate views. VMware workloads are distinct from the Bareos File Daemon proxy that performs their backups.

## Implementation phases

The canonical sequence, task-level checklist, dependencies, and current status are maintained in [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md).

1. Project tracking and environment discovery (P00–P01).
2. Local monitoring and enterprise UI (P02).
3. Application PostgreSQL persistence (P03).
4. Confirmed Run/Cancel and separate live acceptance (P04).
5. Read-only VMware inventory browsing (P05).
6. Verified recovery points and supported restore workflows (P06).
7. Policy management, controlled provisioning, and Add to backup (P07).
8. Application identity and scoped permissions (P08).
9. Protection policy evaluation, durable alerts, and reports (P09).
10. Operational hardening and release acceptance (P10).
11. Selected optional expansion (P11).

Read-only inventory is deliberately separated from configuration writes so it can be delivered before onboarding. Authentication is required before remote or multi-user release. This phase split preserves the agreed feature scope; it does not claim that future features are implemented.

## Domain rules

- Separate job definitions from job sessions identified by JobId.
- Successful backups and verified restores are separate indicators.
- Recovery points must account for backup dependencies and media availability.
- Never display unknown or stale status as healthy.
- External inventory is required to detect machines not registered in Bareos.
- Do not derive filesystem capacity solely from Pool metadata.
- Explain Catalog retention, media data retention, and recycling separately.
- Do not promise Veeam capabilities such as instant VM recovery without verified backend support.

## Acceptance criteria

Statuses match the Director; permission scopes apply to every data path; timeouts are reconciled before redispatch; restores include dependencies; media requirements are visible; restore verification is supported by actual evidence.

## Adding VMware workloads

See [VMWARE-ONBOARDING.md](VMWARE-ONBOARDING.md) for the inventory browser, Add to backup wizard, integration boundaries, and acceptance criteria.

The first release uses explicit VM selection. Folder/tag-based automatic enrollment is a later capability requiring separate rules, exclusions, previews, and audit behavior. Being discovered in vCenter does not mean a VM is protected.

## Current implementation status

Monitoring, application PostgreSQL persistence, and confirmed local Run/Cancel controls are implemented. Operational requests are journaled and audited, with conservative Unknown handling and Director status reconciliation. The release remains single-operator and loopback-only. VMware inventory and local account roles are now implemented. Recovery inspection/gated export code, draft policy editing, onboarding previews and observed alerts/reports are implemented. Live restore, controlled provisioning apply, policy compliance/notifications and production acceptance remain future/in-progress phases. See [OPERATIONS.md](OPERATIONS.md) and [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md) for verification boundaries.

## Per-job schedule editing

Jobs → Edit schedule is the primary entry for a single approved VMware job. It now supports daily, selected weekdays, selected dates each month, monthly ordinal weekdays such as 4th Saturday, hourly intervals within a reviewed backup window, after-job dependencies, optional run-on-failure behavior, and automatic retry count/delay. Full runs use the reviewed cadence for the selected mode; later interval runs in the same window become Incremental. Interval calendars require a reviewed window end. In after-job mode, an optional window end only limits when the dependency trigger may start the run; it is not a promised finish deadline. Monthly dates 29–31 do not run in shorter months. Times remain after 21:00 WITA under the existing operational constraint. Existing priorities and serial execution remain preserved. Retention and maximum volumes remain per job, with complete-chain cleanup safeguards. Preview and explicit confirmed Apply are required. Server-helper synchronization and live apply plus scheduled-run acceptance remain separate work.

## Planned job retirement

Expose distinct Disable schedule, Delete job configuration and Delete backup data workflows. Configuration deletion preserves backup data by default and must retain enough managed identity/resource information for recovery and retention ownership. Backup-data deletion is a separate destructive workflow with explicit chain/media impact review. Shared resources and job dependencies require ownership checks before removal. Track implementation and live acceptance separately in P07-039 and P06-035 of the roadmap; these actions are not implemented yet.

## Planned operational lifecycle expansion

The approved planning backlog includes general job editing (P07-040), job cloning (P07-041), temporary VM maintenance/exclusion (P07-042), repository administration and storage-access probes (P07-043), an upcoming backup calendar (P09-018), full backup-server disaster recovery beyond the application database (P10-019), independent secondary backup copies (P11-013), and periodic backup-integrity checks (P06-036).

Complete the create/edit/disable/clone/delete lifecycle after the scheduling slice. Make full backup-server recovery a production acceptance requirement. Preserve the existing one-VM-per-job design until a verified membership/resource model supports another structure. A second copy must be recoverable independently, and integrity depth must distinguish metadata inspection, data readability/checksums and guest/application recovery. Each capability requires its own implementation, automated/isolated checks and selected live acceptance. These items are planned, not delivered.
