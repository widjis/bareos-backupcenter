# Backup Server Recovery Draft

## Scope and boundary

This draft covers recovery of the inspected Bareos backup server itself, not DR acceptance. It uses only documented evidence from `ARCHITECTURE.md`, `SERVER-DISCOVERY.md`, `OPERATIONS.md`, `DATABASE.md`, and roadmap items `P10-019` and `P10-020`. No backup, export, restore, dump, remote command, or service action was executed.

## Evidenced inventory

- Host OS: Ubuntu 22.04.4 LTS, timezone `Etc/UTC`.
- Bareos install: self-compiled Bareos Director 25.1.1 under `/opt/bareos/25.1.1`.
- Catalog: PostgreSQL-backed Bareos Catalog `MyCatalog`; Director listens on loopback.
- VMware path: local `bareos-fd` acts as proxy with the Python VMware plugin and VDDK installation present. Exact plugin paths and VDDK version/license evidence are undocumented.
- Storage: CIFS/SMB repository mounted at `/mnt/bareos-smb`; about 40 TB, 47% used at inspection.
- Jobs: seven configured VM jobs (the earlier discovery inventory listed six; PNET was added later), each with its own FileSet, Storage resource, and Pool.
- Schedule baseline: Full on days 1 and 15, Incremental on other days, 13:30 UTC / 21:30 WITA.
- Retention baseline: per-VM Pool `Volume Retention 30 days`, `Maximum Volumes 6`, `Recycle enabled`, `AutoPrune disabled`.
- Existing hooks: `prepare-vm-backup` validates the CIFS mount and per-VM directory; before Full it changes used Append volumes for that VM to Used. A separate chain-retention timer runs at `13:20 UTC / 21:20 WITA` and plans pruning while preserving the latest successful Full chain. Script paths are not evidenced.
- Application database: separate PostgreSQL 14.22 `backupcenter` database; not the Bareos Catalog. Runtime uses restricted generated `BACKUPCENTER_DB_*` settings. Public CA file is stored in ignored `.local/postgres-ca.pem`.
- Application auth scope: local authenticated accounts with `Admin`, `Backup Operator`, and `Viewer` roles are documented.
- Root helper evidence: reviewed helper flows retain before-images and outcome receipts, and apply only reviewed changes plus validation/reload/reconciliation steps. Exact receipt paths, helper paths, sudoers scope, and signing/custody evidence are undocumented.

## Ordinary configuration manifest

Recover these items from off-server custody before host rebuild:

- Bareos configuration tree for Director, Storage Daemon, File Daemon proxy, job/FileSet/Pool/Storage resources, schedules, and gateway integration files. Exact file paths under `/etc/bareos` are only partly evidenced.
- Gateway source/config for `/opt/bareos-api/gateway.py` and `bareos-restapi.service`.
- CIFS/SMB mount configuration and any boot-time mount unit or fstab entry for `/mnt/bareos-smb` (exact mechanism unknown).
- Retention/pruning and pre-job script manifests, including timer/unit definitions and VM allowlists.
- Trusted public certificates and CA files required for PostgreSQL TLS and application trust. Private keys belong under secret recovery, not ordinary manifests.

## Encrypted secret recovery

Recover separately, with dual control where possible:

- Bareos API/WebUI credentials stored server-side, including `/root/bareos-credentials.env`, `/root/bareos-hermes-api-credentials.json`, and additional secret-bearing files under `/etc/bareos`.
- Any private certificate keys, signing keys, helper sudo/root authorization material, and encrypted password stores.
- Application database runtime password stored only in ignored `.env`.
- VMware/VDDK entitlement records and any non-redistributable installer media or license proofs. Current docs confirm presence, not redistribution rights.

Do not mix these secret artifacts into ordinary configuration exports or logs.

## Recovery prerequisites

- Clean Ubuntu 22.04 host prepared with matching or explicitly approved Bareos version strategy. Current docs evidence 25.1.1 only.
- Catalog backup/recovery source, application database backup/recovery source, and secret custody materials available. Current docs do not evidence completed backup procedures for these items.
- One designated operator owns the recovery window to prevent duplicate scheduler execution.

## Clean-host recovery order

1. Provision OS, hostname/networking, time sync, and storage mount prerequisites.
2. Restore SMB mount configuration and confirm repository visibility without starting scheduled backup activity.
3. Reinstall or restore Bareos 25.1.1 binaries and companion services.
4. Restore Bareos configuration, gateway files, retention/pre-job scripts, timers, certificates, and helper materials.
5. Recover Bareos Catalog and separately recover the application PostgreSQL database.
6. Restore application auth/runtime configuration and public trust files.
7. Start only the minimum services needed for validation, keeping automatic scheduling disabled until reconciliation completes.
8. Reconcile Catalog, media, mounts, identities, and helper receipts before enabling regular scheduling.

## Duplicate scheduler prevention

- Keep the failed/original host powered off or with Bareos, timers, and helper-driven apply flows disabled before starting the replacement host.
- Do not enable automatic schedules until the replacement host has reconciled Catalog state and confirmed sole ownership of `/mnt/bareos-smb`.
- Review timer- or helper-driven retention/apply units separately from Bareos schedules.

## Catalog and media reconciliation

- Confirm the restored Catalog points to `MyCatalog` content and matches observed job/resource names.
- Verify Pool, Volume, and Storage identities against repository contents on `/mnt/bareos-smb`.
- Review latest successful Full chains and ensure retention scripts do not prune from stale assumptions after host replacement.
- Confirm all seven known VM jobs, per-VM FileSet/Storage/Pool mapping, and proxy-client model remain consistent.

## Isolated recovery acceptance checklist

- Disposable isolated host used; no production scheduler overlap.
- Repository mounted read-only first, then validated for expected volume visibility.
- Bareos configuration restored and syntax/reload checks completed with recorded evidence.
- Catalog restored and reconciled with visible media inventory.
- Application database restored separately and Backup Center can read persisted state.
- One representative non-destructive inspection or controlled test restore path is reviewed in isolation. Exact command set remains unknown.
- Existing schedules, timers, and helper actions remain blocked until reconciliation is signed off.

## Prioritized open questions

1. What exact off-server backup method and custody location will protect the Bareos Catalog, application database, and configuration manifests?
2. What are the exact filesystem paths, systemd unit names, and sudo/helper receipt locations for pre-job, retention, and policy-apply helper flows?
3. What VDDK version, installer media custody, and license terms are required to lawfully rebuild VMware backup capability on a clean host?
4. What is the approved method to disable all automatic scheduling and timers during recovery without losing configuration fidelity?
5. What recovery objectives and representative restore test must be accepted before production go-live?
