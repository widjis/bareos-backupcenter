# Bareos Server Discovery

Inspected on 2026-10-14. Read-only discovery; no backup, restore, configuration change, or service restart was requested.

## Verified environment

- Ubuntu 22.04.4 LTS; server timezone Etc/UTC.
- Bareos Director 25.1.1, self-compiled binaries, installed under `/opt/bareos/25.1.1`.
- Director, Storage Daemon, PostgreSQL, and Apache were active at inspection.
- Director listens on loopback; PostgreSQL Catalog is MyCatalog.
- VMware backups use the local `bareos-fd` client as a proxy, with the Python VMware plugin and VDDK installation.
- Six configured VM jobs: MTIMRWZTNA01, MTIMRWPGSQL01, MTIMRWNTP02, MTIMRWNTP01, MTIMRWKF01, MTIMRWCNTDEV.
- Each VM has its own FileSet, Storage resource, and Pool.
- CIFS storage is mounted at `/mnt/bareos-smb`; reported size 40 TB, 47% used at inspection. These are rounded filesystem figures.
- Schedule: Full on days 1 and 15; Incremental on other days; 13:30 UTC / 21:30 WITA.
- Per-VM pools: Volume Retention 30 days, Maximum Volumes 6, Recycle enabled, AutoPrune disabled.
- Pre-job preparation scripts exist; their cleanup and retention behavior has not yet been inspected.

## Existing API

A FastAPI/Uvicorn gateway runs on loopback port 8000 under `bareos-restapi.service`, with `/bareos-api` configured as its root path. The gateway source is `/opt/bareos-api/gateway.py`.

The upstream OpenAPI describes Bareos REST API version 0.0.1 as experimental. JWT authentication succeeded using the existing server-side credential file. Read-only requests returned HTTP 200 for Director version, jobs, job configuration, and storage configuration.

Available route families include clients, jobs, logs, files, volumes, pools, schedules, storage, and Director version/time. The schema also lists mutation routes; schema presence is not proof that these operations are permitted or tested.

The gateway serializes HTTP calls to prevent interleaved console replies. It blocks DELETE requests, security configuration routes, configuration writes, and selected volume operations. Its health route returns static service information and does not prove Director connectivity.

The `hermes-api` Bareos profile grants broad resource access and several operational commands. Backend permission scoping must be designed before exposing this account through the new application.

## Credential locations

SSH connection settings were used during discovery and subsequently removed from the local `.env`; only API integration settings are retained. Server-side WebUI credentials are in `/root/bareos-credentials.env`; existing API credentials are in `/root/bareos-hermes-api-credentials.json`. Additional integration credential files exist under `/etc/bareos`.

No secret values are included in this document. Credentials were not copied into project documentation.

## Observed execution evidence

Director status reported no running backup jobs at inspection. Recent history included successful full and incremental backups for MTIMRWCNTDEV and a successful full backup for MTIMRWZTNA01. An earlier MTIMRWCNTDEV backup failed. Small smoke-test restore jobs also completed.

These results do not establish successful backups for all six configured VMs or verified VMware recovery. No VM recovery was performed during discovery.

## Design implications

1. Model workload identity separately from the Bareos Client. Six VM workloads share one proxy client; a Client-only inventory would misrepresent protection.
2. Separate file recovery and VMware recovery workflows. VM disk backup records must not be presented as ordinary guest file restore capability.
3. Evaluate reuse of the existing API behind an application adapter; do not build a duplicate integration before checking response contracts and permission behavior.
4. Use capability discovery because the API is experimental and the gateway intentionally restricts operations.
5. Convert UTC schedules explicitly to the selected display timezone.
6. Inspect pre-job scripts and chain-retention behavior before designing policy editing or media cleanup.
7. Validate BVFS, pagination/filtering, remote HTTPS certificate trust, and permission boundaries before implementation.

## Verification limits

Authenticated API checks were performed over server-local loopback. Remote HTTPS access and certificate validation have not been tested. API mutation routes, VMware restore, full inventory coverage, application-consistent backups, and retention correctness remain unverified.
