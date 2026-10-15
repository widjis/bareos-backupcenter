# Local Development

## Requirements

Node.js compatible with Next.js 16 (the implementation was verified with Node 26.8.1), npm, and Python 3.9 or newer. Use the project virtual environment. The application supports local accounts and roles while remaining loopback-only. Remote hosting has not been accepted.

## Setup

Run from the project root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm ci
```

The existing `.env` is user-maintained and must not be overwritten. For a new installation, copy `.env.example` to `.env` and supply the five API settings. No variable should use a `NEXT_PUBLIC_` prefix for credentials. The backend validates HTTPS certificate trust and requires the token endpoint to share the API origin.

## Initial application login

Apply additive migrations with `.venv/bin/python scripts/bootstrap_database.py`, then run `.venv/bin/python -m scripts.bootstrap_admin`. Read the initial Admin username/password from the ignored local `.env` settings; no credentials are printed. Sign in and manage accounts in Settings. See [AUTHENTICATION.md](AUTHENTICATION.md). VMware browsing additionally requires the backend-only connection settings described in [INVENTORY.md](INVENTORY.md).

## Run

```sh
bash scripts/dev.sh
```

Open http://127.0.0.1:3000. Backend: http://127.0.0.1:8001. Both bind to loopback. Stop with Ctrl+C. Restart the backend after changing `.env`; settings are loaded when the adapter initializes.

For separate terminals:

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
npm run dev
```

## Verify

```sh
.venv/bin/python -m pytest backend/tests -q
npm run typecheck
npm run format:check
npm run build
```

Browser tests use Playwright as development tooling only. Use an existing Chromium executable by setting `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, or install Playwright Chromium if no compatible browser exists. With both local servers running:

```sh
npm run test:e2e
```

The live-data browser test expects the currently configured VMware workload names. Failure-state tests use synthetic intercepted responses and never mutate the Bareos server. Automated accessibility checks are included but do not establish full WCAG conformance.

## Data and operational boundaries

- Fixed read routes provide health, snapshots, session logs, audits, and the operation journal. Confirmed typed identity routes and POST /api/operations are enabled; arbitrary Bareos commands and configuration writes are rejected.
- Reads use upstream GET. Token acquisition uses POST; explicit confirmed Run/Cancel dispatch uses the installed API POST/PUT contracts.
- Snapshot source requests are serialized to respect the existing gateway. Data is cached in memory for 15 seconds; the UI refreshes every 60 seconds while visible.
- A full connection failure retains the last snapshot with a stale label; partial source failures identify unavailable sources.
- Session history is bounded to 200 records. When the upstream total exceeds the limit, the adapter requests the final window and sorts by JobId. UI pagination and search operate on that snapshot, not the complete Catalog.
- VMware inventory uses stable connection-scoped UUID/MoRef identities. Existing FileSet name/folder associations remain provisional; they are not automatically approved assignments.
- Recorded backups are not verified recovery points. No RPO, restore, media-chain, VM boot, or application-consistency guarantee is inferred.
- Storage resources are logical Bareos objects. Filesystem capacity and physical repository mapping are not live telemetry in this release.
- Local sessions and Admin/Backup Operator/Viewer permissions are implemented. Keep loopback binding; remote hosting requires separate TLS, access-scope and deployment acceptance.

## Troubleshooting

If the UI cannot load data, check that both processes are running, the server is reachable, credentials are valid, and the configured PEM trusts the HTTPS endpoint. TLS verification is never disabled as a fallback. Partial-source errors appear in the connection banner. Logs are fetched only when a session is opened and are redacted before returning to the browser.

## Application persistence

The existing PostgreSQL host was provisioned with a dedicated `backupcenter` database. Runtime settings are generated as `BACKUPCENTER_DB_*`; host `POSTGRES_*` settings are used only by the bootstrap script. See [DATABASE.md](DATABASE.md) for schema, permissions, TLS, and provisioning.

The backend loads the saved snapshot on startup and preserves its original timestamp if Bareos is unavailable. Settings displays database health, observation counts, and collector audit history. If PostgreSQL is unavailable, live read-only monitoring continues with an explicit persistence warning.

Database migration/bootstrap:

```sh
.venv/bin/python scripts/bootstrap_database.py
```

## Run and Cancel

The backend starts the database-elected operation worker. A queued request continues after the browser closes; restarting during dispatch produces Unknown rather than resending. See [OPERATIONS.md](OPERATIONS.md) before testing live actions. Automated mutation tests use intercepted/simulated responses and do not exercise real job side effects.

## Current workflow verification

Migrations 002–008 add inventory, local identity, constrained isolated-restore intents, draft policies, observed alerts, and dry-run provisioning revisions/assignments. Backend/bootstrap restarts load the local settings. Report/alert evaluation uses collected observations; closing the UI does not create an always-on notification collector. Provisioning apply now stages a durable rehearsal that writes temporary local fixtures only and records a `provision` journal entry; it does not modify Bareos configuration or reload the Director. Live restore remains disabled; the approved helper/receipt integration is installed but scope is absent and the helper remains unexecuted. See RESTORE-TARGET-PROPOSAL.md before any server setup.

The worker fault check `.venv/bin/python -m scripts.verify_worker_recovery` uses a separate PostgreSQL namespace, mocked Director I/O and administrator cleanup of its own fixture rows. It is an integration check, not a real backup/cancel/restore test. Do not run live commands merely to satisfy a roadmap checkbox.

## Windows local startup — verified 2026-10-15

From PowerShell in the project root, run:

```powershell
.\scripts\dev.ps1
```

The launcher starts hidden loopback-only frontend/backend processes and records logs and launcher PIDs under ignored `.local/`. If a port is occupied it does not kill or replace the existing process; verify that it belongs to this application. This is a local development process, not an installed production service. It does not enable backup or restore dispatch.

Windows requires `.venv\Scripts\python.exe`, installed frontend dependencies, and Node.js on PATH. Install `tzdata` into the virtualenv for IANA timezone support on Windows. The existing `.env` had a macOS PostgreSQL CA path; it now points to `.local/postgres-ca.pem` in the Windows checkout. The public certificate was retrieved over SSH using an already trusted host key. Database SSL verification remains enabled. No database bootstrap/migration or credential reset was performed.

Initial Admin login settings remain in ignored `.env` (`BACKUPCENTER_ADMIN_USERNAME` / `BACKUPCENTER_ADMIN_PASSWORD`). Do not copy them into documentation or browser source.
