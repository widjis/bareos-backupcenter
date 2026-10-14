# VMware Inventory and Onboarding

## Objective

Allow an operator familiar with Veeam to browse VMware inventory and explicitly add selected VMs to backup protection while the existing Bareos installation remains the backup engine.

## Inventory browser

Entry point: Infrastructure -> VMware.

Select a vCenter connection, browse datacenters and folders, and search or filter VMs. Table fields include VM name, folder, power state, assigned backup policy, protection status, and last successful backup. Additional host, cluster, and disk information appears only when available from the inventory integration.

Support explicit checkbox selection, server pagination, retained selection across pages, and a visible selected-VM summary. Display inventory synchronization time and connection errors. Distinguish empty inventory, no search results, permission-limited visibility, and unavailable inventory.

A VM may be discovered but unassigned, configured and awaiting its first backup, protected according to freshness requirements, overdue, or unknown. A configured job alone does not establish protection.

## Add to backup wizard

1. Select VMs: confirm stable identities and detect existing assignments.
2. Select policy: show backup scope, required capabilities, and exclusions.
3. Select schedule and repository: display timezone, backup levels, proxy mapping, and capacity information when known. Inherited settings are clearly labeled.
4. Review: show selected VMs, generated resources, schedule, repository, configuration diff, and required preparation/retention script allowlist additions. Report unsupported plugin or provisioning capabilities before submission.
5. Apply and track: create an operation, provision validated resources, and verify that the Director has loaded them. The current implementation stages a durable dry-run rehearsal only; live Director load remains pending. Show per-VM outcomes and partial failures.

Completion means Configured / Pending first backup. Running the first backup is a separate explicit action. A later successful backup updates protection status according to policy.

## Integration model

Browser -> Application backend -> VMware inventory adapter/service -> vCenter.
Browser -> Application backend -> Controlled provisioning service -> Bareos configuration and Director.
Browser -> Application backend -> Existing Bareos API -> Job status and history.

The current API-only local credentials support monitoring. Future inventory and provisioning credentials are introduced only for the selected integration method and remain backend/server-side.

## Identity and reconciliation

Store the vCenter connection ID and stable VM identity; retain instance UUID and managed object reference where available. Never join workloads solely by VM name. Reconcile current name/folder with plugin-supported targeting. Rename or move conflicts must be surfaced without silently creating a second backup assignment.

Map existing six VMware jobs to their workloads and shared backup proxy before adding new VMs. Treat ambiguous matches as review-required. Repositories represent physical/logical destinations separately from Bareos Storage and Pool resources.

## Provisioning safeguards

- Authorize the user, policy, VMs, proxy, repository, and schedule server-side.
- Validate typed parameters; do not accept raw console commands or configuration fragments from the browser.
- Inspect existing preparation and chain-retention scripts before generating new resource mappings.
- Use configuration revisions and coordinated operations; protect unrelated resources.
- Revalidate inventory and the configuration revision before apply.
- Check Bareos syntax and dependencies before loading changes.
- Reconcile uncertain outcomes before retrying; prevent duplicate assignments.
- Provide per-VM results, audit records, and a partial-failure recovery path without promising cross-system atomicity.
- Never delete backup history or media as an implicit onboarding rollback.

## Later: folder/tag-based enrollment

A future policy may include a folder or tag with explicit exclusions. Preview matching VMs, define synchronization cadence and enrollment behavior, and audit membership changes. Decide separately what happens when a VM leaves the group; do not silently remove jobs or backup data. This is outside the initial explicit-selection release.

## Acceptance criteria

- Existing VM workloads are represented separately from the shared proxy client.
- Duplicate names in different inventory locations do not select the wrong VM.
- Renamed or moved VMs are reconciled by identity or flagged for review.
- Selection remains accurate across search, pagination, and refresh.
- TLS or authentication failure never produces a successful empty inventory.
- Configuration writes remain unavailable until a verified provisioning service exists.
- Concurrent edits, double submissions, and timeouts do not create duplicate assignments.
- Partial failure provides an accurate per-VM result and recovery path.
- A new assignment is Pending first backup until qualifying execution evidence exists.
- No existing job, schedule, credential, media, or retention behavior changes during design work.

## Delivery status

Read-only inventory, stable identifiers, PostgreSQL persistence, VMware browse/selection UI, draft policy previews, and durable dry-run apply staging are implemented; see INVENTORY.md and POLICIES-AND-PREVIEWS.md. The controlled live provisioning service and accepted Add to backup workflow remain pending. Real read-only inventory verification does not establish provisioning, backup or recovery acceptance.

## Discovered provisioning dependency

The existing preparation and chain-retention scripts have explicit allowlists of the current six VMs. Future onboarding must extend these through reviewed, validated provisioning rather than merely adding Job/FileSet resources. The current Run/Cancel release does not modify those scripts.
