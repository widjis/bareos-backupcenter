# Lifecycle Persistence

`backend/lifecycle_store.py` adds a PostgreSQL-backed durability adapter for lifecycle Clone and retirement flows. It is designed to wrap the existing application `Store`, reuse its connection factory and `connection_id`, delegate `actor_allowed`, and forward other unknown methods back to the wrapped store.

## Tables introduced by migration 011

- `backupcenter.lifecycle_operations`
  - shared durable receipt journal for Clone and retirement
  - unique `(connection_id, idempotency_key)` across both actions
  - stores actor, action, review digest, target identity, state, intent, and sanitized result
- `backupcenter.lifecycle_operation_claims`
  - per-target claim rows used to serialize unresolved Clone and retirement work
  - unresolved `Prepared`, `Dispatching`, and `Unknown` claims keep blocking the target
- `backupcenter.lifecycle_retirement_records`
  - stores retirement discovery metadata and retained recovery references
  - keeps private before-image metadata separate from API-visible status

## Operational rules

- Clone `Dispatching` is committed before any external executor call.
- A second identical Clone idempotency key does not return a fresh claim. The store raises and the caller must read the durable existing receipt instead of dispatching again.
- Clone `Applied` and `Failed` release claims; `Unknown` keeps them for reconciliation.
- Retirement `Prepared` is created atomically with the target claim.
- A second identical retirement idempotency key also raises instead of returning a reusable prepared claim, preventing a second external delete attempt.
- `save_retirement_record()` commits a private before-image receipt and advances the durable state to `Dispatching` before deletion starts.
- `finalize_retirement_operation()` uses terminal-state CAS semantics. Once a retirement becomes `Unknown`, later attempts do not overwrite it to `Applied`.
- Cross-connection reads and writes are fully scoped by `connection_id`.
- Advisory claim locks are sorted before acquisition to avoid A->B / B->A deadlocks across multi-claim Clone requests.

## Before-image privacy

The store does not persist raw configuration content into API-visible receipts. If the executor provides a `content` field, the adapter now requires an opaque durable helper handle such as `receiptId`, `captureId`, `referenceId`, `handle`, or an equivalent helper receipt/reference object. Path and digest alone are not treated as durable crash-recovery proof. Status reads and retired-job discovery never expose raw before-images.

## Migration privileges

Migration `011_lifecycle_journal.sql` grants only the runtime privileges needed by this adapter:

- `SELECT, INSERT, UPDATE` on `backupcenter.lifecycle_operations`
- `SELECT, INSERT, UPDATE` on `backupcenter.lifecycle_retirement_records`
- `SELECT, INSERT, DELETE` on `backupcenter.lifecycle_operation_claims`

No blanket `DELETE` privilege is granted on operations or retirement records.

## Intended coordinator wiring

Small coordinator change only:

1. Instantiate the normal application `Store`.
2. Wrap it with `LifecycleStore(existing_store)`.
3. Use the wrapper wherever lifecycle Clone/retirement receipts are needed.

This keeps existing app persistence behavior intact while adding:

- `CloneStore` / `CloneStoreTransaction`
- `DurableRetirementStore`
- delegated `actor_allowed`
- existing `Store` methods via attribute forwarding

## Verification in this batch

Offline tests executed:

- `.venv\Scripts\python.exe -m pytest -q backend\tests\test_lifecycle_store.py`

Observed result: `8 passed`.

No migration was applied in this batch. No remote database writes, production lifecycle execution, backup deletion, or schedule acceptance were performed here.


## Coordinator integration and real PostgreSQL acceptance

Migration 011 has now been applied to the existing application database and its exact checksum verified. The gateway uses `compose_lifecycle_store()` to preserve the operational Store while adding registry identity and durable Clone/retirement protocols. External idempotency keys use connection-scoped UUID5 internal operation IDs; committed or rolled-back transactions close their connection. Opaque native `opaqueRef` before-image handles survive storage without raw configuration content.

The final adapter passed six acceptance checks against a uniquely owned isolated PostgreSQL schema using actual SQL, independent connections and the runtime role: concurrent repeated claims, same external key across connections, Unknown target locks, retirement repeated claims, terminal CAS/isolation, and operation-receipt DELETE denial. The probe verified ownership and removed its schema. This is database acceptance; no native Clone, retirement, backup or restore was dispatched. `scripts/check_lifecycle_store_postgres.py` documents the reproducible probe.
