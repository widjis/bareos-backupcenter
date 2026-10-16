"""Reconcile current authenticated Director/vCenter identities; default is read-only.

This updates application identity metadata only. It never starts jobs or changes Bareos files.
"""
import argparse
import asyncio
import json
from pathlib import Path

from backend.lifecycle_foundations import database_foundation_status
from backend.managed_registry import ManagedRegistryRepository, reconcile_managed_registry
from backend.persistence import Store

ROOT = Path(__file__).resolve().parents[1]


async def collect_current_sources():
    from integration.collect_managed_registry import _remote_config, _build_observed, _retired_assignments
    from backend.app import SOURCES, gateway, inventory as current_inventory
    import httpx
    g = gateway()
    async with httpx.AsyncClient(verify=g.context, timeout=20, trust_env=False) as client:
        director = await g.get(client, SOURCES["director"])
    inventory = await current_inventory().snapshot(True)
    workloads = list((await g.snapshot(True)).get("workloads", []))
    raw = {"director": director}
    config = await asyncio.to_thread(_remote_config)
    retired = await asyncio.to_thread(_retired_assignments)
    return _build_observed(raw, inventory, workloads, config, retired)


async def reconcile_live_registry(store, *, apply=False, collector=collect_current_sources, repository_factory=ManagedRegistryRepository, readiness=database_foundation_status):
    database = readiness(store)
    repository = repository_factory(store)
    initial = repository.enumerate_entries() if database["registryStoreReady"] else []
    expected = {str(row["stable_id"]): row["revision"] for row in initial}
    observed = await collector()
    retired = repository.read_retired_assignments() if database["registryStoreReady"] else []
    candidate = reconcile_managed_registry(observed, retired)
    output = {"mode": "apply" if apply else "read_only", "status": candidate["status"], "managedJobCount": len(candidate["entries"]), "database": database, "blockers": candidate["blockers"]}
    if candidate["status"] != "ready":
        return output, observed
    if apply:
        if not database["registryStoreReady"]:
            output.update(status="blocked", blockers=[{"code": "missing_registry_schema", "summary": "Reviewed managed-registry schema must be applied before metadata reconciliation."}])
            return output, observed
        receipt = await asyncio.to_thread(repository.reconcile, observed, expected_revisions=expected)
        output.update(status=receipt["status"], receiptId=receipt["id"])
    return output, observed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        output, observed = await reconcile_live_registry(Store(), apply=args.apply)
        artifact = ROOT / ".local/lifecycle-production-b6/registry-reconciled-source.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(observed, sort_keys=True, default=str), encoding="utf-8")
        print(json.dumps(output, default=str))
        return 0 if output["status"] in {"ready", "Applied", "Replay"} else 2
    except Exception:
        print(json.dumps({"status": "blocked", "error": "Authoritative registry reconciliation failed. No Bareos job changes were requested; inspect source and metadata receipts before retrying."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
