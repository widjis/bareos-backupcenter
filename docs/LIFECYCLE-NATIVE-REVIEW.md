# Coordinator native review before deployment

No native candidate installed. Do not activate apply or perform real mutations.

1. Windows remote Python command must set PYTHONPATH=/opt/bareos/25.1.1/lib/bareos/vmware-python (real import pyVim otherwise fails). POSIX invoke must route resource executor actions as well.
2. Capabilities require exact contract plus expected reviewed local SHA256 for helper, resource executor, policy and required dependencies, secure root file modes/parents and true locks. Never trust installedReady alone or fallback transportReady to installedReady. All errors generic/redacted, no raw stderr/config.
3. Resource executor currently own /run lock differs lifecycle /var/lib/bareos/vm-chain-retention.lock and after_job runtime per-target lock. Mutations need shared locks including policy/retention and source/target delivery, scan unresolved receipts/active jobs/catalog, authoritative full loaded resource/inboundhook coverage. Unknown/missing proof blocks.
4. Native clone currently accepts a canonical payload without independently verifying source registry/VM/repository binding. Require exact bound fresh server proof or block. New disabled/manual VM candidate must be confirmed actually loaded; SD device changes require safe SD reload/readback (Director reload alone insufficient).
5. Retirement functions currently lack actor/intent/review binding and durable native delete/restore receipts. capture/delete/read/restore must be exact scoped and idempotent, locked, CAS, durable before writes, and loaded absence/readback verified. Current restore accepts arbitrary root JSON opaqueRef and overwrites current file: constrain receipt path, symlinks, owner, content digest, actor/intent and destination CAS. Preserve all data/resources except exact Job file.
6. Keep beforeimages root-only; no arbitrary rmtree cleanup. Replay return shape must match clone service state applied/unknown/failed and never include raw beforeimages. Store coordinator now supports opaqueRef.
7. Current native tests 8pass/2fail: runtime pending expects exception but review returns blocked; clone success is unknown. Backend regressions excluding executor:269passed/5failed/1skip, failures lifecycle_api transportPOSIX assumption plus realhelperfixture resource dependency causing409 preparation. Fix genuine production behavior; coordinator owns existingtests but fixtures may need explicit fake resource module/capabilities. Do not weaken realproduction capability proof to satisfyfixtures.

Use project .venv Python; run full backend tests after fixing, do not edit applied010/011, app/foundations/collector/store files. No deletes then recreates. Native installation remains coordinator-reviewed separate step.


## Current coordinator checkpoint

The main gateway now attaches production collectors and adapter objects. Fresh database privilege checks and the explicit lifecycle flag independently gate execution. The flag remains0. The installed helper has not been replaced by this candidate. Authenticated local registry/foundations endpoints return HTTP200 with seven entries and native installed/apply=false. Removal review remains HTTP200/blocked/executionSupported=false. The coordinator corrected the five existing API/worker fixture failures through explicit resource dependency injection and removal of the old POSIX-only transport assumption; thirteen affected tests passed. The latest native-inclusive suite still has one native Clone success-fixture failure. These changes do not resolve the native deployment findings above.

At the last bridge check, the existing native execution3e301cefeb8859c59829106cacedcec0 in conversation2e032a9cf8ea450fa45e8ec20db8164d was still in_progress. The connector refuses follow-up during a running execution; do not create a replacement conversation or blindly resubmit. Once it completes, reuse that conversation with the findings above, then review changes and rerun tests. No installation or real lifecycle operation has been accepted by this checkpoint.


## Native hardening follow-up dispatched

The original execution completed on2026-10-16. The same conversation was reused for execution97cd9db29047399ea32fb4875a5717e1 (request bareos-prod-b6-executor-hardening-20261016-02), explicitly requiring items1-7 above and no installation/mutations. Review its result before any deployment. Also verify that new lifecycle claims and the existing operation_requests journal serialize conflicting Clone/retirement versus Disable/Enable actions; collector reads alone cannot close a concurrent claim race.

Final regression checkpoint for completed components:286passed/1skipped with test_lifecycle_executors.py explicitly excluded because native hardening remains active. The prior native-inclusive run retained one Clone fixture failure; no all-green native-suite claim is made. Final local gateway reload succeeded after identifying the extra Windows conhost child. Authenticated registry and foundations endpoints still return HTTP200, seven jobs and native installed/apply=false. Removal review is blocked. No dispatch settings changed.
