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

## Live PNET pilot — 2026-10-15 (UTC+8)

The operator approved PNET only (instance UUID `5208e076-eb89-9f06-2ef2-790ac92b4d71`, MoRef vm-29087). The earlier RDS test selection was superseded and never modified. The pilot preserves PNET's original poweredOn state and does not expose VM power operations.

The existing wizard now distinguishes `mode=live` from rehearsal. Admin selects PNET, reviews dedicated folder/device/Pool/Job resources and fixed policy, then chooses **Enable backup for PNET**. A stable request key, durable claim and a root-owned typed SSH helper apply the reviewed digest. No arbitrary shell/config/path is accepted. Other VMs remain rehearsal-only until separately approved in the root UUID scope and backend settings. A staged assignment is Retired after successful handoff to native Director configuration; that retires the staging record, not VM protection. Fresh inventory then resolves the configured UUID identity.

Root helper: `/opt/bareos-api/apply_onboarding.py`; contract: `/opt/bareos-api/onboarding_contract.py`; scope: `/opt/bareos-api/backupcenter-onboarding-scope.json`; receipts/rollback copies: `/var/lib/bareos-onboarding/`. Existing daemon configuration-directory permissions are unchanged. It checks fresh UUID/name/power/snapshot state, mount/free space, configuration collisions and idle backup state, writes exact root-owned resources, validates Director/Storage syntax, restarts Storage and reloads Director, and records a receipt. Apply never starts a backup. Ambiguous delivery becomes Unknown and is not retried automatically.

The fixed policy uses VMwareTwiceMonthly (Full on 1/15, Incremental other days, 21:30 UTC+8), serial priority 16 after the original six jobs, and the existing complete-chain 30-day retirement model. Dedicated directory: `/mnt/bareos-smb/PNET` / `F:\Backups\BareOSBackup\PNET`. Preparation and retention name mappings were extended, including the original SQL prefix filters that would otherwise exclude PNET. No cleanup command was executed during verification.

Acceptance: actual browser selection/review/Apply completed via the app journal. First successful Full was JobId 23, 2026-10-15 12:16:12–12:17:29 UTC+8, duration 77 seconds, 4,473,713,156 backup bytes, six files and zero errors. Volume PNET-0009 contains 4,474,615,853 bytes. PNET remained poweredOn; CBT is enabled, temporary snapshots are absent, consolidation is not required. The operator subsequently approved one Incremental test: JobId 24 succeeded on 2026-10-15 14:36:58–14:37:08 UTC+8, 7,925,206 bytes and zero errors. Recovery inspection resolved Full 23 → Incremental 24 on PNET-0009 without Catalog blockers. PNET remained poweredOn, CBT enabled, no snapshots and no consolidation required. Actual restore, media readability and recovered data/boot acceptance remain untested.

Compatibility findings: initial JobId 20 rejected simultaneous UUID/name-path options (zero bytes). Jobs 21/22 exposed missing datacenter/inventory context in Bareos 25.1.1's UUID branch (zero bytes; temporary snapshots cleaned). Generator now uses UUID-only options. A surgical local patch populates datacenter, name and relative folder after UUID resolution; four isolated checks passed. Reproducible patch: `integration/patch_vmware_uuid_context.py`; original plugin backup: `/root/bareos-fd-vmware.py.before-uuid-datacenter-fix`. Name/path lookup used by the original six jobs is unchanged. Plugin upgrades must review/reapply or supersede this compatibility patch and rerun acceptance.

Verification: 63 relevant backend tests, six browser tests and TypeScript checking passed. Operator acceptance of general multi-VM onboarding, configurable policy apply, production deployment and restored VM/data correctness remain open.


## PNET isolated restore acceptance — 2026-10-15

The operator explicitly authorized a restore test of PNET. Source recovery point 24 resolved Full 23 plus Incremental 24 on PNET-0009. The root helper prepared a fresh directory and Bareos write access was verified. A temporary root-owned scope contained only VMware-PNET and was removed immediately after the submission attempt; dashboard restore dispatch remains disabled.

The first API submission returned HTTP 500. Native history confirmed no restore job existed: the command omitted an explicit FileSet and Director reported “No FileSet found for client”. The corrected native console command included fileset=VMware-PNET and created exactly one restore, JobId 25. API console mode dispatched the valid command without an interactive confirmation, even without a trailing yes; future previews must not send restore commands in API mode. The root intent was reconciled to JobId 25 rather than resent. This run used the server helper/native console, not the dashboard restore workflow.

JobId 25 completed Restore OK, status T, zero errors, three restored stream items, 16,044,756,500 reported bytes, 2026-10-15 14:41:51–14:43:37 UTC+8 (106 seconds). Output: `/mnt/bareos-smb/backupcenter-restore-tests/81f30b01-5943-499d-bb9f-a22612632e63/[Local-MTIMRWESX01] PNET/PNET.vmdk`, corresponding to `F:\Backups\BareOSBackup\backupcenter-restore-tests\81f30b01-5943-499d-bb9f-a22612632e63\[Local-MTIMRWESX01] PNET\PNET.vmdk`. The standalone monolithicSparse VMDK is 15,201,140,736 bytes with virtual capacity 107,374,182,400 bytes (100 GiB). Only the VMDK artifact was emitted; three restored items do not mean three output files.

Read-only sparse-grain inspection validated the VMDK magic/descriptor, logical MBR signature, GPT header CRC, GPT partition-array CRC and ext filesystem signature in the 1 GiB partition. These checks establish basic disk-format/metadata readability, not guest-file equivalence, full filesystem integrity or boot/application recovery. PNET remained poweredOn, CBT enabled, no snapshots and no consolidation required. No test VM was registered or powered on. Retain the isolated VMDK for review; no cleanup was requested or performed.

The explicit FileSet fix was added to integration/backupcenter_restore.py, covered by the focused recovery regression suite (8 passed), and installed on the server with rollback copy /root/backupcenter_restore.py.before-explicit-fileset. Only bareos-restapi was restarted and is active. Actual recovery of guest data and isolated boot acceptance remain open; dashboard Windows SSH restore transport remains unaccepted.
