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

- [DATABASE.md](DATABASE.md): isolated application schema, runtime permissions, recovery cache, and provisioning.

- [OPERATIONS.md](OPERATIONS.md): confirmed Run/Cancel workflow, durable dispatch, audit, and verification boundaries.

- [INVENTORY.md](INVENTORY.md): actual VMware inventory, identity and browsing contracts.
- [AUTHENTICATION.md](AUTHENTICATION.md): local roles, login and initial account setup.

- [RECOVERY.md](RECOVERY.md): inspection, isolated export gates and acceptance.
- [POLICIES-AND-PREVIEWS.md](POLICIES-AND-PREVIEWS.md): draft policies and no-apply onboarding review.
- [ALERTS-AND-REPORTS.md](ALERTS-AND-REPORTS.md): observed alerts, scoped CSV and print-page reports.
- [RESTORE-TARGET-PROPOSAL.md](RESTORE-TARGET-PROPOSAL.md): blocked helper deployment proposal.

## Next steps

Follow [IMPLEMENTATION-ROADMAP.md](IMPLEMENTATION-ROADMAP.md). The next independent implementation phase is read-only VMware inventory (P05); live Run/Cancel acceptance remains tracked separately in P04.
