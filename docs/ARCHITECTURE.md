# Architecture Proposal

## Proposed stack

React/Next.js with TypeScript for the frontend; FastAPI for the API; python-bareos DirectorConsoleJson for the adapter; an application PostgreSQL database separate from the Catalog; a worker with a persistent queue; SSE for UI updates; Docker Compose for initial internal deployment.

These choices are proposals and have not been validated against the target environment.

## Data flow

Browser -> Application API -> operation queue -> worker -> Bareos adapter -> Director.
Collector -> adapter -> Director; the collector stores metadata in the application database.
The Director manages the Catalog, File Daemons, and Storage Daemons. Backup and restore data flows through Bareos, not through the web API.

## Data ownership

Bareos: jobs, sessions, media, and execution results.
Application: inventory, groups, owners, protection targets, alerts, audit records, and metadata cache.

## Operations

Pending -> Dispatching -> Accepted -> Running -> Completed/Failed.
An unknown outcome must be reconciled against the Director before retrying. An API idempotency key does not guarantee exactly-once acceptance by the Director.

## Access control

Enforce server-side authorization and map permissions to Bareos Console/Profile/ACL resources. Use least-privilege accounts and prohibit raw console commands from the browser. Keep secrets on the server. Validate TLS and certificates. Apply user scopes to caches and SSE events.

## Required discovery

Director version; plugins; TLS; ACLs; JSON responses; BVFS; restore configuration; storage types; capacity metrics. Enable features based on verified capabilities.

## References

- https://docs.bareos.org/master/DeveloperGuide/PythonBareos.html
- https://download.bareos.org/current/BareosMainReference/DeveloperGuide/api.html
- https://docs.bareos.org/master/IntroductionAndTutorial/BareosWebui.html

## Confirmed application boundary

Backup Center is a separate application providing a modern interface and operational workflows. The existing Bareos installation remains the backup and restore engine and owns its Catalog and backup media.

The application backend will validate permissions, normalize data, track operations, and integrate with the existing Bareos REST gateway where its capabilities have been verified. Direct python-bareos integration remains an option for capabilities the gateway does not expose. The browser must never connect directly using privileged Bareos credentials.

Integration settings and credentials have been consolidated into the local project `.env`, which is excluded from Git and restricted to owner read/write permissions. The monitoring backend reads only the API base URL, token endpoint, username, password, and TLS trust certificate from the user-maintained `.env`. Other settings, if present, are not used by this release. Runtime integration uses the existing API; credentials are never sent to the browser.

The API trust certificate is stored as `BAREOS_API_TLS_CA_PEM`. Server-side certificate paths are not local runtime settings. Remote HTTPS trust still requires validation before deployment.

## VMware inventory and controlled provisioning

The application backend will read inventory through a dedicated VMware inventory adapter or a server-side inventory service. Existing Bareos REST endpoints do not establish vCenter discovery capability. Inventory access uses validated TLS and least-privilege read access. VMware credentials may remain on the integration server; they are not required in the current local `.env` for monitoring.

Persist workload identity independently of Bareos Client identity. Scope identifiers to the vCenter connection and retain instance UUID and managed object reference where available. VM name and folder are display/plugin attributes, not globally unique identifiers. Verify the installed plugin's identifier support before selecting how generated FileSets reference VMs.

Onboarding requires a controlled provisioning service because the existing gateway blocks configuration writes. Do not bypass that guard by exposing privileged raw commands. The service must accept typed, validated requests, check authorization and resource names, create a configuration diff, validate Bareos configuration, apply coordinated changes, and reconcile the loaded resources. Repository mapping includes proxy, Storage, Pool, and media type; onboarding does not automatically require a new physical repository or per-VM storage resource.

Use revision checks, operation IDs, locking, and idempotent reconciliation to prevent duplicate configurations and conflicting updates. Preserve unrelated resources. Partial failures must be visible, with explicit compensation or operator recovery; do not claim atomicity across application state, configuration files, and Director reloads.

Before implementing provisioning, inspect the existing pre-job preparation scripts and chain-retention service. This design does not authorize replacing their behavior. Direct VMware inventory access and provisioning service deployment remain unimplemented and unverified.

## Implemented monitoring stage

The initial monitoring stage used Next.js, FastAPI, and the existing REST gateway with process-memory snapshots and visible-page polling. The implemented persistence phase below adds PostgreSQL; workers, queues, SSE, application authentication, and operational writes remain proposed components. See [IMPLEMENTATION-REPORT.md](IMPLEMENTATION-REPORT.md) for verified behavior and limits.

## Database decision for the monitoring release

Do not introduce an application database solely for the read-only view redesign. Bareos remains the source of job and media data; losing the transient cache on restart is acceptable. Introduce a separate PostgreSQL database when implementing durable policy state, inventory identity mapping, application access control, audit history, or operations requiring restart-safe reconciliation. Do not use the Bareos Catalog for application-owned state.

## Implemented persistence phase

A separate application PostgreSQL database is now configured. It stores normalized snapshots, observed workload mappings, session observations, and append-only collector events. The reserved operation journal schema is present but no operational commands are dispatched. Persistent recovery cache is loaded after backend restart; monitoring remains available with a warning when persistence fails. Host SSH credentials provision the database; a restricted generated PostgreSQL role is used at runtime. See [DATABASE.md](DATABASE.md).

## Implemented operational controls

The backend now hosts a single-leader durable operation worker elected through PostgreSQL. Confirmed Run/Cancel intents are persisted before dispatch, serialized with the Director adapter, audited, and reconciled by JobId. Unknown deliveries are not automatically retried. The browser polls the bounded journal; restore and configuration writes remain disabled. See [OPERATIONS.md](OPERATIONS.md).

## Implemented inventory and local identity

Direct backend pyVmomi inventory, UUID/MoRef persistence and server-paginated browsing are implemented; see [INVENTORY.md](INVENTORY.md). The backend now also reads the user-maintained VMware connection settings. Local application identities, role checks and verified request actors replace the trusted local-operator label; see [AUTHENTICATION.md](AUTHENTICATION.md). These sections supersede earlier phase-specific statements about unimplemented inventory/authentication. All services remain loopback-only. Restore/provisioning and production deployment are still separate acceptance scopes.

## Draft policy, observed-alert and recovery extensions

The application now persists revisioned draft policies and observed failure/warning alerts, with bounded historical report/CSV queries. These are separate from accepted assignments, RPO compliance, notification delivery and live media validation. Typed recovery gateway extensions preserve the existing configuration-write guard. A proposed narrow root target helper remains local-only after automatic review rejected deployment; see RESTORE-TARGET-PROPOSAL.md. Controlled provisioning apply and production deployment remain unimplemented/unaccepted.
