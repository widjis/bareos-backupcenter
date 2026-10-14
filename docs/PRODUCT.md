# Product Brief

## Goal

Help operators identify protected machines, address operational issues, monitor backup schedules, and restore files. Provide workflows familiar to Veeam users while retaining access to the underlying Bareos resource mappings.

## Navigation

- Overview: protection summaries, active sessions, and alerts.
- Jobs: backup definitions, policy assignments, schedules, and operational actions.
- Backups: backed-up workloads, recovery points, and restore entry points.
- Infrastructure: VMware inventory, backup proxies, repositories, and advanced media details.
- History: backup/restore sessions, logs, and reports.
- Settings: connections, users, permissions, notifications, and audit access.

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
