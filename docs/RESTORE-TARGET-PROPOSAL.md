# Isolated Restore Target Helper Proposal

Status: explicitly approved installation and receipt integration deployed; live target preparation and restore acceptance deferred by the operator.

## Reason

The integration API user does not have traversal/write access to the original CIFS share. Giving that service broad membership in the Bareos filesystem group would expand access to existing backup/configuration data. The proposed alternative is one root-owned typed helper that creates only a new isolated request directory after checking an administrator-approved job scope.

Automatic approval review rejected the attempted helper deployment on 2026-10-15 because it modifies protected server/API files and can prepare restore directories. Broad implementation authorization was not considered sufficient for those live infrastructure effects. The rejected command did not execute. The operator subsequently explicitly approved the named installation and receipt integration. Deployment proceeded under that authorization; no target preparation was executed.

## Review artifacts

- [prepare_restore_target.py](../integration/prepare_restore_target.py): root-only preparation program.
- [test_restore_target_review.py](../backend/tests/test_restore_target_review.py): non-root, extra-field, absent-scope and JSON-parser checks.
- [backupcenter_restore.py](../integration/backupcenter_restore.py): gated isolated-export API implementation with root-owned receipt validation.

## Proposed deployment and boundary

Install `/opt/bareos-api/prepare_restore_target.py` as root-owned mode 0700. The deployed integration replaces API-side share writes with a verified root-owned preparation receipt. The API service would retain its existing Unix groups and would not gain general NAS/configuration access.

Installation alone must not execute target preparation, create the approval file, enable backend restore settings, create directories, or dispatch a restore. Before activation, obtain the chosen test job/destination approval, recheck current permissions and share availability, integrate and test receipt checks, and record the deployment/rollback hash.

When explicitly activated and invoked, the helper accepts only `job_id` and a canonical UUID `request_id`. It verifies root execution, the root-owned non-writable approval file, a completed Backup session in the approved job list, the CIFS mount, and the fixed restore-root identity. It atomically creates a new UUID directory under `/mnt/bareos-smb/backupcenter-restore-tests/`; existing request directories are rejected. It never accepts an arbitrary path or modifies an existing VM, volume, job, or schedule.

A root-owned, API-group-readable receipt would be stored in `/opt/bareos-api/restore-preparations/`. The API would validate its source JobId, UUID, destination and ownership before the fixed local-VMDK command. File Daemon/Bareos owns data restoration. Overwrite remains Never. A lost preparation response requires reconciliation; an empty directory must not be reused automatically.

## Current acceptance boundary

The named installation/integration is approved and deployed. Live preparation, backup/restore and provisioning are explicitly deferred. No approval scope or receipt directory exists, no helper invocation occurred, and application restore dispatch remains disabled. Destination write permissions, export content and VM boot recovery remain unverified. Controlled provisioning implementation remains open.

## Deployed verification

The helper is root-owned mode 0700. API readiness passed after restart. Tests cover non-root invocation, unexpected fields, absent scope, canonical UUID, disabled SSH transport, and exact root-owned receipt validation. The API rejects missing, mismatched or writable receipts before the Director command; it receives no general NAS group access. Receipt ownership checks use an opened no-follow descriptor. The helper transport is one-shot after the durable Dispatching claim; an uncertain outcome is never resent.
