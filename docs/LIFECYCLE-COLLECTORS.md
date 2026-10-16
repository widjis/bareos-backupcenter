# Lifecycle Collectors

`backend/lifecycle_collectors.py` provides the read-only production collectors used by `backend.lifecycle_extra_api.py` for clone and retirement review.

## Scope

- `collect_clone_review(source_job_name, new_job_name, new_vm_uuid, repository_id, trusted_role)`
- `collect_retirement_proof(job_name, trusted_role)`

The collectors never write managed-registry rows, retirement records, clone receipts, or native configuration. They only assemble authoritative review inputs from:

- current managed-registry state
- current authenticated native config and inventory sources
- Store-backed operations and observed history
- scoped retained-recovery references for the exact job

## Clone collector

The clone collector builds the server-owned `snapshot` and `registryEvidence` contract required by `backend.lifecycle_clone.review_clone_candidate()`.

It verifies or reports:

- exact current managed assignment from the managed registry
- current authenticated source freshness and coverage
- all loaded job names for namespace conflict checks
- current fileset / pool / schedule namespace for clone draft resources
- current managed assignments for duplicate target-VM protection
- target VM uniqueness and visibility in authenticated inventory
- target repository availability from authenticated native config
- unresolved operations, partial dependency proof, and unverified retired conflicts

The collector never guesses VM identity from job name alone and never copies secrets.

## Retirement collector

The retirement collector builds the full proof contract required by `backend.lifecycle_retirement.review_retirement()` and `execute_retirement()`.

It verifies or reports:

- exact current managed assignment and stable identity
- exact current job config path and digest from managed-registry proof
- current ownership and usage for job / FileSet / Pool / Storage / Schedule
- unresolved lifecycle operations and observed runtime activity
- partial or missing dependency / hook proof
- retained recovery references scoped to the exact job only
- missing Catalog visibility or missing retention / cleanup ownership as explicit blockers

`mediaReadableVerified` remains `False` unless an injected retention provider can prove it independently.

## Injection points

`ProductionLifecycleCollectors` accepts optional injection for:

- `store`
- `registry`
- `source_bundle_provider`
- `retention_provider`

The default source-bundle path reuses the managed-registry native collection helpers in memory and does not write any local artifact.

## Current limitations

- Retention and cleanup ownership are intentionally fail-closed. Without an injected authoritative provider, retirement review remains blocked.
- The default monitoring/history source is the persisted Store snapshot. Coordinators may inject a fresher retention provider if they already have stronger exact-job Catalog evidence.
- The collectors sanitize outputs to names, digests, paths, ownership counts, and stable references only. Raw config content and secrets are excluded.
