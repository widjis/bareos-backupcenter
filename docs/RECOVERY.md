# VMware Recovery Inspection and Isolated Export

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
