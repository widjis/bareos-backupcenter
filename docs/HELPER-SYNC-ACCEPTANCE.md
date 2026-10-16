# Helper Synchronization and PNET Acceptance — 2026-10-16

## Installed scope

Seven reviewed contract/helper/runtime/systemd files were installed on the existing Bareos server using exact UTF-8 LF source hashes. The installer first validates an idle Director, no unresolved policy receipt, current scheduling baseline, exact target set, candidate syntax and target modes. Before-images are private and each replacement is atomic. General Apply remains blocked.

Latest helper rollback directory: `/root/backupcenter-helper-sync/20261016T070847Z-b2e70b1d`. Original pre-sync helpers are retained under `/root/backupcenter-helper-sync/20261016T070210Z-159f0e29`. Installer receipts record before-existence, owner/group/mode, checksums and Installed state. Do not restore helper bytes without also reconciling any later policy before-images.

## Actual PNET result

An unscheduled temporary Admin source was used for one explicitly controlled Incremental PNET acceptance; no other VM was backed up. Source JobId37 expanded `%i` correctly and native runtime receipt acknowledged target JobId38. Exact Catalog lookup confirmed Job38 belongs to VMware-PNET. It completed successfully (T), zero errors, 25,151,998 bytes, six plugin files, 07:05:46–07:05:55 UTC / 15:05:46–15:05:55 WITA. This one-shot manual acceptance did not change ordinary backup start times.

The strict Admin-source response parser did not establish its JobId, so the controller persisted Unknown and did not resend. Source name/type/baseline and runtime receipt uniquely reconciled it to Job37. Replay returned the existing target Job38; Catalog confirmed exactly one PNET run after preparation. The exact temporary source config was removed after digest verification, syntax/reload and baseline hash checks. Native Catalog history and acceptance receipts are retained.

Acceptance evidence directory: `/var/lib/bareos-pnet-acceptance-f2513752-8523-48fc-a0d7-980d739c24f3`. This is separate from the production drain state directory.

## Controlled policy Apply

PNET policy receipt `5833207e-1c05-4cc1-b5b3-4f922631c584` is Applied with native schedule/Pool read-back and idempotent replay. Definition: Full1/15, Incremental other days, 21:30 WITA, retention30/max6. Only PNET job config and BC-Policy-PNET schedule content changed; all unselected config hashes remained intact.

An initial preview was stopped because it included shared retention-code migration despite unchanged retention. Coordinator fixed planning so a schedule-only intent does not migrate that script. Explicit retention changes still show the reviewed migration in their plan. The accepted PNET Apply left the shared retirement script unchanged.

## Verification and remaining approval

209 backend tests passed, one skipped; isolated helper fixture and three installer rollback/checksum fixtures passed. Authenticated local current API returned HTTP200, helperCompatible=true, general Apply=false, PNET schedule BC-Policy-PNET. No broad UI Apply activation or normal 21:30 clock-triggered acceptance is claimed.

Earlier in this batch, automatic approval review rejected persistent timer activation because explicit human approval had not yet been supplied. That rejection remains part of the history and was not bypassed.

After the human explicitly approved permanent activation, the coordinator rechecked the default runtime queue and candidate hashes through the existing root wrapper before changing systemd state. The default receipt queue under `/var/lib/bareos-after-job-runtime/receipts` was empty, and all seven installed candidate hashes matched `/tmp/backupcenter-native-b4-qs5vodz6/install-manifest.json` without printing helper file contents. The coordinator then ran `systemctl enable --now backupcenter-after-job-drain.timer` and `systemctl start backupcenter-after-job-drain.service` through `Invoke-BareosRemote.ps1 -Root -Command <script>`.

Verified result: `backupcenter-after-job-drain.timer` is now enabled and active with `SubState=waiting`; `backupcenter-after-job-drain.service` finishes as a oneshot with `Result=success` and `ExecMainStatus=0`; `/var/lib/bareos-after-job-runtime` exists as `bareos:bareos` mode `0700`; Bareos Director, Storage Daemon and File Daemon remained active; and the default receipt queue stayed at zero. A natural timer trigger was observed with `LastTriggerUSec=Fri 2026-10-16 07:26:00 UTC` and `NextElapseUSecRealtime=Fri 2026-10-16 07:27:00 UTC`. The bounded polling used only natural elapsed time and did not inject receipts or start any new backup, restore or policy Apply.

Broad execution readiness still remains false. This activation does not close ordinary 21:30 clock-triggered acceptance, broad lifecycle gates, or the remaining Catalog identity edge acceptance.
