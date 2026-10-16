# Managed Registry

`backend/managed_registry.py` introduces a dedicated registry for existing live managed VMware jobs. It is intentionally separate from `protection_assignments`, because onboarding rows in `Prepared` / `Failed` / `Retired` represent staged policy work, not authoritative proof of current live ownership.

## Stored identity

Each registry entry is bound to:

- exact current `job_name`
- verified VMware `instance_uuid`
- current inventory connection identity
- exact current Bareos storage / repository, FileSet and Pool binding
- selector provenance proving how the VM was resolved (`uuid` or exact `vmname + folder + dc`)
- monotonic registry `revision`
- sanitized `configuration_digest`
- lifecycle state (`enabled`, `disabled`, or `manual_only`)

The stable identifier is derived from the authenticated inventory connection identity plus the verified VM UUID. It is never created from job-name inference alone.

## Reconciliation rules

The reconcile service fails closed when any of these proofs is missing or ambiguous:

- stale, invalid, or future source freshness timestamps
- stale or partial Director, inventory, or config source coverage
- missing or non-unique VM UUID
- duplicate job name or duplicate VM UUID across observed managed jobs
- incomplete resource accounting for job / FileSet / Pool / Storage / Schedule / JobDefs usage
- mismatch between authenticated loaded Director resources and current disk resources
- unknown FileSet include-path expansion
- conflict with an old `Retired` onboarding assignment for the same job or VM, except for verified released staging rows (`Validated` revision with `payload.liveApplied=true`)
- rename/conflict evidence that would require guessing ownership

All config evidence stays sanitized: paths, digests, names, dependency links, selector provenance, and usage counts are stored; raw config text, plugin secrets, and remote helper source are not.

## Repository contract

`ManagedRegistryRepository` uses the existing `Store.connect()` factory and `connection_id`:

- `read_retired_assignments()`
- `assignment_detail(job_name)`
- `enumerate_entries()`
- `proof_snapshot(job_name)`
- `reconcile(observed, expected_revisions=None)`

`assignment_detail(job_name)` is shaped for the current lifecycle manager adapter path.

Before any reconcile write, the repository also re-reads authoritative persisted inventory and blocks if the supplied `inventory_vm_id`, `inventory_connection_id`, `instance_uuid`, visibility, selector match, or current `vcenterUuid` does not match the stored inventory snapshot.

## Live source collection

`integration/collect_managed_registry.py` performs a read-only collection pass:

1. current Director configuration via the existing gateway API
2. current VMware inventory via the existing inventory helper
3. authenticated loaded Director resources plus sanitized disk path/digest metadata via the reviewed remote wrapper

The collector resolves managed VMware jobs from authenticated FileSet selectors:

- direct `uuid`
- exact `vmname + folder + dc`

Name-only matching is not accepted. A selector must resolve to exactly one visible inventory VM with `identityQuality == "instance-uuid"`.

The collector writes a sanitized source artifact and never changes Bareos configuration. Its current inventory helper refreshes the existing application inventory cache in PostgreSQL. Managed registry reconciliation remains a separate explicit operation.


## Applied production checkpoint

Migration 010 is applied and its SHA256 is verified in the existing migration ledger. The coordinator CLI `scripts/reconcile_managed_registry.py` defaults to read-only and accepts `--apply` only for application registry metadata. On 2026-10-16 it registered seven existing VMware jobs against current authenticated inventory; a second fresh pass returned Replay with seven stable IDs and unchanged revision 1. The old released PNET staging row was retained. The main gateway now composes the registry-backed assignment adapter with the durable lifecycle Store. Admin-only GET `/api/jobs/lifecycle/registry` exposes a sanitized bounded list; `/api/jobs/lifecycle/foundations` reports database and native readiness independently. Native execution acceptance remains separate.
