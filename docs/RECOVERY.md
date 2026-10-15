# VMware Recovery Inspection and Isolated Export

## Current direct-VM restore status — 2026-10-15

The end-to-end new-VM restore workflow is implemented for seven root-approved managed sources, with actual restore/boot acceptance currently limited to PNET. Admin chooses live datacenter/folder/host/datastore, reviews current source-chain/target evidence, confirms any valid unique new VM name, and monitors the existing durable operation journal. The new VM is created without any Ethernet adapters and stays powered off. Existing VM names and datastore directories are rejected; destination names are reserved across requests. Targets and required capacity (backed-up virtual disks plus reserve and memory) are rechecked before the durable one-shot command. Root scope is /opt/bareos-api/direct-vm-restore-scope.json, currently containing all seven managed VMware jobs (see the expansion evidence below); further expansion is an explicit administrator action.

The opt-in compatibility patch reads a root-owned no-follow receipt, removes source UUID addressing only for that request, and redirects to the reviewed destination. Ordinary backup UUID handling is preserved. It rejects pre-existing targets and removes NICs before CreateVm. The gateway refuses execution if this patch is unavailable. Inputs never become arbitrary console commands; only validated source resource tokens and canonical IDs are composed. MAC/UUID regeneration is expected when the source VM still exists and may produce native Warning status.

Supported scope: new VM, one source disk-datastore mapping, Never overwrite, no NIC, powered off. Multi-datastore disk mapping, original-VM overwrite, arbitrary NIC reconnection, guest-file recovery, instant recovery and application-item recovery remain unsupported. Guest data/application validation is independent of OS-boot acceptance. Existing local VMDK export uses its independent flag/scope.

API: GET /api/recovery/vmware/targets; POST /api/recovery/vmware/plan; POST /api/recovery/vmware/restore with source_job_id, typed destination, review_digest, idempotency_key and confirmed=true; GET /api/operations/{id}; GET /api/recovery/vmware/result/{id}. Admin and existing same-origin protection apply. Submission digest/key bind source, destination and resolved target refs; changed reviews are rejected. Unknown delivery is never resent automatically. Root receipts live under /var/lib/bareos-vm-restore and preserve acceptance failures and successes.

Acceptance: dashboard operation 39f7035d-09fc-410a-9520-dbbeff537be4 / request 11c7b074-253a-41a9-9d89-c200c50b2733 created RestoreFiles JobId 27 from source 24 (chain 23 + 24). Native Restore OK -- with warnings, zero errors, three restored stream items, 16,044,756,500 bytes, 15:40:38–15:42:07 UTC+8 (89 seconds). Warnings concern generation of new MAC/UUID due to the still-existing original. VM PNET-RESTORE-TEST is vm-32506, instance UUID 5009413f-1183-85a8-1143-eb9d89cff648, host mtimrwesx01.mbma.com, datastore Local-MTIMRWESX01, folder /. Original PNET vm-29087 remained poweredOn with no snapshot; test VM has zero NICs and no snapshot.

A separately recorded isolated boot succeeded: guestState=running and guestToolsRunning, boot time 2026-10-15 07:43:29 UTC. The test VM was returned to poweredOff. Guest OS/name/disk telemetry was not populated in that observation window, so no guest-file checksum or application validation is claimed. Execution/isolation and boot proofs are returned separately by the result API and shown for recovery point 24 in the dashboard. Keep the restored test VM and earlier isolated VMDK for review; no deletion was requested.

Earlier JobId 26 failed before VM creation (zero bytes) because restore plugin options omitted config_file. Native history was reconciled and the failed receipt preserved. Added config_file=/etc/bareos/vmware-plugin.ini, then submitted a new separately reviewed request. No unknown request was retried.

## Implemented scope

Backups -> Inspect recovery reads the Director-resolved Full/Differential/Incremental JobId chain, deduplicated Catalog volume mappings, pruning flags, and VMware disk/firmware items. Guest-file, original-VM, instant-VM, and application-item recovery are unavailable. Catalog media presence is not a read test or a recovery guarantee.

An additive gateway extension supplies fixed authenticated read-only commands: llist jobid, .bvfs_get_jobids, and list jobmedia. The existing configuration-write guard remains in place. A bounded chain must belong to the same Catalog client/FileSet; missing sources or inaccessible metadata fail explicitly. Original REST file metadata supplies bounded VMDK/NVRAM item output.

A typed isolated-export command, durable journal handling and confirmation UI are implemented. The only mode is localvmdk=yes to a new UUID path beneath /mnt/bareos-smb/backupcenter-restore-tests/, with replace=never. JobId chains and configured client/storage references are revalidated. Namespace reuse, non-VMware sources and unsafe resource/path values are rejected. Accepted/Running/Completed describe Director execution, never content verification.

Live dispatch remains disabled. The operator explicitly approved installation of the narrow root helper and receipt integration, which are deployed. The API retains its existing Unix groups and performs no share writes. No scope file exists, the helper was not executed, and no receipt directory was created. All live target preparation, backup/restore and provisioning operations are deferred by operator instruction. Actual destination permissions and recovery content remain unverified; see [RESTORE-TARGET-PROPOSAL.md](RESTORE-TARGET-PROPOSAL.md).

## Journal and request safety

Migration 005 constrains restore intents to a positive canonical JobId, fixed vm-disks-isolated mode, Never overwrite, and the exact UUID-keyed destination. Database actor authorization and Dispatching claim share a transaction/row lock. Known rejection fails; timeout, HTTP 500, incomplete acknowledgement and interruption remain Unknown and are never resent automatically. Explicit browser retries retain the same key.

No temporary BVFS file-selection table is created for this whole-VM-item mode. The selected source is the immutable backup JobId, content is the complete disk/firmware set, and the destination is generated rather than user-supplied. Arbitrary directory/file/version selection remains a separate pending workflow.

## Verification

Read-only chain and export-plan checks succeeded on actual completed JobId 17. Real Catalog item metadata contained a VMDK and NVRAM item. Config/chain/media inspection is not restore execution. Backend tests cover pruning, missing Full/media, Catalog windows, scoped typed reads, fixed export parameters, Admin-only dispatch, HTTP 500/timeout and no resend. Browser export submissions were fully intercepted. Real PostgreSQL intent constraints and actor denial were tested in rolled-back transactions.

A separate process-interruption check used mocked Director I/O and an isolated PostgreSQL namespace; a new worker recovered Dispatching to Unknown without resend. Fixtures were removed by the administrator. The real Director operation journal stayed empty.

Primary restore syntax reference: [Bareos Restore Command](https://docs.bareos.org/bareos-22/TasksAndConcepts/TheRestoreCommand.html).

All job mutations additionally require `BACKUPCENTER_OPERATION_DISPATCH_ENABLED=1`. Its local value is 0 under the current operator deferral. Setting only the restore-specific flag cannot activate dispatch. Do not activate either flag during the deferred acceptance period.


## PNET isolated restore acceptance — 2026-10-15

The operator explicitly authorized a restore test of PNET. Source recovery point 24 resolved Full 23 plus Incremental 24 on PNET-0009. The root helper prepared a fresh directory and Bareos write access was verified. A temporary root-owned scope contained only VMware-PNET and was removed immediately after the submission attempt; dashboard restore dispatch remains disabled.

The first API submission returned HTTP 500. Native history confirmed no restore job existed: the command omitted an explicit FileSet and Director reported “No FileSet found for client”. The corrected native console command included fileset=VMware-PNET and created exactly one restore, JobId 25. API console mode dispatched the valid command without an interactive confirmation, even without a trailing yes; future previews must not send restore commands in API mode. The root intent was reconciled to JobId 25 rather than resent. This run used the server helper/native console, not the dashboard restore workflow.

JobId 25 completed Restore OK, status T, zero errors, three restored stream items, 16,044,756,500 reported bytes, 2026-10-15 14:41:51–14:43:37 UTC+8 (106 seconds). Output: `/mnt/bareos-smb/backupcenter-restore-tests/81f30b01-5943-499d-bb9f-a22612632e63/[Local-MTIMRWESX01] PNET/PNET.vmdk`, corresponding to `F:\Backups\BareOSBackup\backupcenter-restore-tests\81f30b01-5943-499d-bb9f-a22612632e63\[Local-MTIMRWESX01] PNET\PNET.vmdk`. The standalone monolithicSparse VMDK is 15,201,140,736 bytes with virtual capacity 107,374,182,400 bytes (100 GiB). Only the VMDK artifact was emitted; three restored items do not mean three output files.

Read-only sparse-grain inspection validated the VMDK magic/descriptor, logical MBR signature, GPT header CRC, GPT partition-array CRC and ext filesystem signature in the 1 GiB partition. These checks establish basic disk-format/metadata readability, not guest-file equivalence, full filesystem integrity or boot/application recovery. PNET remained poweredOn, CBT enabled, no snapshots and no consolidation required. No test VM was registered or powered on. Retain the isolated VMDK for review; no cleanup was requested or performed.

The explicit FileSet fix was added to integration/backupcenter_restore.py, covered by the focused recovery regression suite (8 passed), and installed on the server with rollback copy /root/backupcenter_restore.py.before-explicit-fileset. Only bareos-restapi was restarted and is active. Actual recovery of guest data and isolated boot acceptance remain open; dashboard Windows SSH restore transport remains unaccepted.


## Direct VMware planning slice — 2026-10-15

Backups → Inspect recovery now includes an Admin-only “Restore as a new VMware VM” destination form. Review accepts a new name, datacenter, absolute VM-folder path, ESXi host and datastore. Power off, disconnected network and Never overwrite are fixed typed values. The endpoint /api/recovery/vmware/plan reuses current chain/media inspection, checks configured plugin addressing and returns a deterministic intent digest, required media and precise blockers without any console command or mutation. Manual target names are unverified; no direct restore dispatch endpoint or VM creation exists yet. Existing disk-export behavior remains independent.

Live read-only review of PNET point 24 resolved [23,24] and PNET-0009, detected UUID addressing and returned dispatchEnabled=false. Compatibility with a new target, actual vCenter topology/capacity/permission validation and disconnected-network enforcement remain unfinished. Do not interpret the review as a successful VMware restore or change the backup FileSet merely to dismiss UUID detection: existing backup metadata compatibility must be verified.


## Watching a restore

After submitting a restore, an observed progress panel appears automatically once Bareos returns a JobId. A reloaded page also discovers running restore operations. To inspect an existing job, open History and select its RestoreFiles session; the same panel appears in session details. The panel refreshes status, elapsed time, observed Catalog counters and log tail approximately every 3 seconds. Terminal status stops polling. Error/connection loss preserves and labels stale values. Percent complete and ETA are unavailable; unchanged Catalog byte counters do not prove a stalled restore. No extra restore is needed to open a completed session.


Restore names no longer require the source-name/-RESTORE prefix. On 2026-10-15, read-only preflight accepted PNET-TEST2-RESTORE in DC /Development on mtimrwesx02.mbma.com / MTIMRWME5024. Existing PNET remained rejected by the VM-name collision check. Syntax, source scope, datastore directory collisions, reserved names, isolation and Never overwrite remain enforced. No restore was executed for this verification.


History shows the destination VM name when an exact JobId-to-operation mapping exists, while the drawer retains the native Bareos job name. The progress panel includes expandable warning explanations and original redacted messages. Identity-change warnings are explanations of observed log entries, not assertions that unrelated warnings are harmless or that guest applications are verified.

## Seven-job restore scope — 2026-10-15

The operator authorized expansion to the six other managed VMs. The authoritative root allowlist `/opt/bareos-api/direct-vm-restore-scope.json` now contains VMware-MTIMRWZTNA01, VMware-MTIMRWPGSQL01, VMware-MTIMRWNTP02, VMware-MTIMRWNTP01, VMware-MTIMRWKF01, VMware-MTIMRWCNTDEV and VMware-PNET. A nonsecret deployment reference is maintained at `integration/direct-vm-restore-scope.json`; install as root-owned mode 0600 only within authorized scope. The previous server file was preserved under `/root/direct-vm-restore-scope.before-expansion-<timestamp>.json`.

Live `targets` returned all seven jobs. Read-only plans for recovery points 12, 13, 14, 15, 16, 17 and 24 respectively all returned Ready for confirmation. Chains were [11,12], [13], [14], [15], [16], [17] and [23,24]. Destination checks used DC, /Development, mtimrwesx02.mbma.com and MMSMRWQNAP01, with unique `<VM>-RESTORE-CHECK-20261015` probe names. Required capacity including reserve/memory ranged from 65,498,251,264 to 135,291,469,824 bytes; destination free capacity was 15,206,490,046,464 bytes. These are point-in-time checks, repeated at actual review/dispatch.

An attempted read-only plan naming the existing MTIMRWZTNA01 was rejected as an existing VM; no overwrite is allowed. All sources retain power-off, zero-NIC, unique-name/directory and single-source-datastore constraints. No restore was dispatched and no VM was created for this expansion. The six additional VMs still require actual restore and guest/application acceptance. Reopen recovery inspection after refreshing the dashboard to load the current scope.
