# Bareos Backup Center

A modern operational dashboard built on top of Bareos for monitoring machine protection, running backups, and restoring files.

## Status

The local monitoring application, PostgreSQL persistence, VMware inventory, local authentication/roles, and confirmed Run/Cancel controls are implemented and connected to the existing Bareos API. See LOCAL-DEVELOPMENT.md for startup and IMPLEMENTATION-REPORT.md for verification and limitations.

## Documentation

- [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md): canonical phased implementation checklist and progress tracker.

- [PRODUCT.md](PRODUCT.md): product scope and implementation phases.
- [ARCHITECTURE.md](ARCHITECTURE.md): architecture and integration boundaries.
- [DESIGN.md](DESIGN.md): visual direction and UI behavior.
- [AGENTS.md](../AGENTS.md): project instructions, including the English documentation requirement.

- [SERVER-DISCOVERY.md](SERVER-DISCOVERY.md): verified server environment and integration findings.

- [VMWARE-ONBOARDING.md](VMWARE-ONBOARDING.md): VMware inventory and explicit VM onboarding design.

- [LOCAL-DEVELOPMENT.md](LOCAL-DEVELOPMENT.md): setup, startup, verification, and operational limits.
- [UX-CONTRACT.md](UX-CONTRACT.md): shared interface behavior and ownership.
- [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md): implementation evidence.
- [ACCELERATION-REVIEW.md](ACCELERATION-REVIEW.md): coordinator acceptance, parallel task state and regression evidence.
- [ACCELERATION-BROWSER.md](ACCELERATION-BROWSER.md): TRAE browser fixture contribution and discovered source regression.
- [ACCELERATION-LIFECYCLE.md](ACCELERATION-LIFECYCLE.md): pure lifecycle preview boundaries and coordinator corrections.

- [DATABASE.md](DATABASE.md): isolated application schema, runtime permissions, recovery cache, and provisioning.

- [OPERATIONS.md](OPERATIONS.md): confirmed Run/Cancel workflow, durable dispatch, audit, and verification boundaries.
- [SCHEDULING-HELPER-SYNC.md](SCHEDULING-HELPER-SYNC.md): concrete pre-deploy package and rollback plan for synchronizing the Bareos scheduling helper.

- [INVENTORY.md](INVENTORY.md): actual VMware inventory, identity and browsing contracts.
- [AUTHENTICATION.md](AUTHENTICATION.md): local roles, login and initial account setup.

- [RECOVERY.md](RECOVERY.md): inspection, isolated export gates and acceptance.
- [POLICIES-AND-PREVIEWS.md](POLICIES-AND-PREVIEWS.md): draft policies and no-apply onboarding review.
- [ALERTS-AND-REPORTS.md](ALERTS-AND-REPORTS.md): observed alerts, scoped CSV and print-page reports.
- [RESTORE-TARGET-PROPOSAL.md](RESTORE-TARGET-PROPOSAL.md): blocked helper deployment proposal.

## Next steps

Follow [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md). The PNET-only live onboarding pilot and its first Full have passed; general onboarding, configurable policy apply and actual restore acceptance remain open. See VMWARE-ONBOARDING.md for the scope and compatibility patch.

- [Scheduling safety audit](SCHEDULING-SAFETY-AUDIT.md)
- [Disable preview evidence adapter](DISABLE-PREVIEW-ADAPTER.md)
- [Backup-server recovery draft](BACKUP-SERVER-RECOVERY.md)

- [After-job durable runtime and activation gates](AFTER-JOB-RUNTIME.md)
- [Disable monitoring evidence collector](DISABLE-COLLECTOR.md)

- [Native scheduling validation evidence](NATIVE-SCHEDULING-VALIDATION.md)
- [Lifecycle proof normalization](LIFECYCLE-PROOF.md)

- [Installed helper and controlled PNET acceptance](HELPER-SYNC-ACCEPTANCE.md)
