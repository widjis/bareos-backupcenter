"""Production lifecycle collectors built from managed registry, native config, inventory, and Store checks.

This module stays read-only: it never writes registry state, receipts, or native configuration.
`collect_clone_review()` returns the server-owned inputs expected by `backend.lifecycle_clone`.
`collect_retirement_proof()` returns the authoritative proof shape expected by
`backend.lifecycle_retirement`.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from backend.managed_registry import ManagedRegistryRepository, _parse_timestamp, reconcile_managed_registry
from backend.persistence import Store


CloneCollected = dict[str, Any]
RetirementProof = dict[str, Any]

_CLONE_COVERAGE = [
    "operations",
    "dependencies",
    "intents",
    "resources",
    "names",
    "assignments",
    "target_vm",
    "target_repository",
]


class RegistryProtocol(Protocol):
    def assignment_detail(self, job_name: str) -> dict[str, Any] | None: ...
    def enumerate_entries(self) -> list[dict[str, Any]]: ...
    def proof_snapshot(self, job_name: str) -> dict[str, Any] | None: ...
    def read_retired_assignments(self) -> list[dict[str, Any]]: ...


class StoreProtocol(Protocol):
    configured: bool
    connection_id: str

    def load(self) -> dict[str, Any] | None: ...
    def lifecycle_operations(self, job_name: str) -> list[dict[str, Any]]: ...


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _resource(code: str, name: str, ownership: str, usage_count: int, proof_revision: int | None) -> dict[str, Any]:
    return {
        "resource_type": code,
        "resource_name": name,
        "ownership": ownership,
        "usage_count": usage_count,
        "proof_revision": proof_revision,
    }


def _intent(kind: str, summary: str, proof_revision: int | None) -> dict[str, Any]:
    return {"kind": kind, "summary": summary, "proof_revision": proof_revision}


def _dependency(relation: str, stable_id: str | None, job_name: str | None, proof_revision: int | None) -> dict[str, Any]:
    if relation not in {"depends_on", "required_by"}:
        relation = "required_by"
    return {
        "relation": relation,
        "related_stable_id": stable_id or "unknown",
        "related_job_name": job_name or "Unknown",
        "proof_revision": proof_revision,
    }


def _ownership(resource: dict[str, Any]) -> str:
    if resource.get("accounted") is not True:
        return "unknown"
    return "exclusive" if int(resource.get("usageCount") or 0) == 1 else "shared"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _session_started(row: dict[str, Any]) -> datetime | None:
    for key in ("started", "starttime", "observedAt", "lastSeenAt"):
        parsed = _parse_timestamp(row.get(key))
        if parsed:
            return parsed
    return None


def _is_successful_backup_session(row: dict[str, Any], job_name: str) -> bool:
    name = str(row.get("name") or row.get("job") or "")
    if name != job_name:
        return False
    if str(row.get("type") or "").lower() not in {"backup", "b"}:
        return False
    status = str(row.get("status") or row.get("jobstatus") or "").lower()
    return status in {"succeeded", "warning", "t", "w"}


def _is_runtime_nonterminal(row: dict[str, Any], job_name: str) -> bool:
    name = str(row.get("name") or row.get("job") or "")
    if name != job_name:
        return False
    status = str(row.get("status") or row.get("jobstatus") or "").lower()
    return status in {"running", "active", "waiting", "queued", "created", "r", "f", "a", "c", "m", "l", "d", "s", "j", "i"}


def _normalize_operation(row: dict[str, Any]) -> dict[str, str]:
    raw_state = str(row.get("state") or "").lower()
    state = {
        "prepared": "prepared",
        "dispatching": "dispatching",
        "accepted": "active",
        "running": "active",
        "waiting": "waiting",
        "unknown": "unknown",
        "completed": "completed",
        "failed": "failed",
        "canceled": "canceled",
    }.get(raw_state, "unknown")
    return {
        "operation_id": str(row.get("id") or row.get("operation_id") or row.get("target") or "unknown"),
        "kind": "lifecycle_apply" if str(row.get("kind")) == "provision" else "other",
        "state": state,
        "summary": ((row.get("parameters") or {}).get("summary")) or f"{row.get('kind', 'operation')} is {raw_state or 'unknown'}.",
    }


def _target_vm_state(inventory: dict[str, Any], new_vm_uuid: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = inventory.get("vms", []) if isinstance(inventory, dict) else []
    if not new_vm_uuid:
        return [], {"targetVmUuid": None, "matchCount": 0, "visible": False}
    matches = [row for row in rows if row.get("instanceUuid") == new_vm_uuid]
    return matches, {
        "targetVmUuid": new_vm_uuid,
        "matchCount": len(matches),
        "visible": bool(matches and matches[0].get("visible", True)),
        "name": matches[0].get("name") if len(matches) == 1 else None,
        "folder": matches[0].get("folder") if len(matches) == 1 else None,
        "datacenter": matches[0].get("datacenter") if len(matches) == 1 else None,
    }


def _repository_options(native_config: dict[str, Any], observed: dict[str, Any]) -> list[dict[str, Any]]:
    names: dict[str, dict[str, Any]] = {}
    loaded_storages = (((native_config.get("loaded") or {}).get("storages")) or {}) if isinstance(native_config, dict) else {}
    for name in loaded_storages:
        names[name] = {"id": name, "label": name, "supported": True}
    for row in observed.get("jobs", []) if isinstance(observed, dict) else []:
        if isinstance(row, dict) and row.get("repositoryId"):
            names[str(row["repositoryId"])] = {"id": str(row["repositoryId"]), "label": str(row.get("storageName") or row["repositoryId"]), "supported": True}
    return [names[key] for key in sorted(names)]


def _native_namespace(native_config: dict[str, Any], proof_revision: int | None) -> tuple[list[str], list[dict[str, Any]], list[dict[str, str]]]:
    loaded = (native_config.get("loaded") or {}) if isinstance(native_config, dict) else {}
    jobs = loaded.get("jobs", {}) if isinstance(loaded.get("jobs"), dict) else {}
    filesets = loaded.get("filesets", {}) if isinstance(loaded.get("filesets"), dict) else {}
    pools = loaded.get("pools", {}) if isinstance(loaded.get("pools"), dict) else {}
    blockers: list[dict[str, str]] = []
    resources: list[dict[str, Any]] = []
    names = sorted(jobs)
    if not names:
        blockers.append(_block("missing_loaded_jobs", "Authenticated loaded jobs are unavailable."))
    for name, row in sorted(filesets.items()):
        selectors = row.get("selectors", []) if isinstance(row, dict) else []
        ownership = "shared" if not selectors else "exclusive"
        resources.append(_resource("fileset", name, ownership, 0 if not selectors else 1, proof_revision))
    usage: dict[str, int] = {}
    for row in jobs.values():
        pool_name = row.get("pool")
        if pool_name:
            usage[str(pool_name)] = usage.get(str(pool_name), 0) + 1
        schedule_name = row.get("schedule")
        if schedule_name:
            usage[f"schedule::{schedule_name}"] = usage.get(f"schedule::{schedule_name}", 0) + 1
    for name in sorted(pools):
        resources.append(_resource("pool", name, "exclusive" if usage.get(name, 0) == 1 else "shared", usage.get(name, 0), proof_revision))
    schedule_names = sorted({str(row.get("schedule")) for row in jobs.values() if row.get("schedule")})
    for name in schedule_names:
        count = usage.get(f"schedule::{name}", 0)
        resources.append(_resource("schedule", name, "exclusive" if count == 1 else "shared", count, proof_revision))
    return names, resources, blockers


def _retained_recovery(snapshot: dict[str, Any] | None, job_name: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    sessions = snapshot.get("sessions", []) if isinstance(snapshot, dict) else []
    if not isinstance(sessions, list):
        sessions = []
    backups = [row for row in sessions if isinstance(row, dict) and _is_successful_backup_session(row, job_name)]
    backups.sort(key=lambda row: _session_started(row) or datetime.fromtimestamp(0, tz=timezone.utc), reverse=True)
    latest_job_ids = []
    for row in backups:
        job_id = _safe_int(row.get("sourceJobId") or row.get("jobId") or row.get("id"))
        if job_id and job_id not in latest_job_ids:
            latest_job_ids.append(job_id)
    catalog_visible = bool(backups) and (snapshot or {}).get("connection") == "connected"
    return {
        "recoveryPointCount": len(latest_job_ids),
        "latestJobIds": latest_job_ids[:25],
        "catalogReferenceIds": [f"catalog:{job_id}" for job_id in latest_job_ids[:25]],
        "catalogVisibilityConfirmed": bool(overrides.get("catalogVisibilityConfirmed", catalog_visible)),
        "stableRecoveryReferencesConfirmed": bool(overrides.get("stableRecoveryReferencesConfirmed", bool(latest_job_ids))),
        "retentionOwnerConfirmed": bool(overrides.get("retentionOwnerConfirmed", False)),
        "cleanupOwnerConfirmed": bool(overrides.get("cleanupOwnerConfirmed", False)),
        "mediaReadableVerified": bool(overrides.get("mediaReadableVerified", False)),
    }


def _global_source_issues(observed: dict[str, Any], native_config: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    candidate = reconcile_managed_registry(observed, [])
    if candidate.get("status") != "ready":
        for item in candidate.get("blockers", []):
            if isinstance(item, dict) and item.get("summary"):
                issues.append(str(item["summary"]))
    coverage = (native_config.get("coverage") or {}) if isinstance(native_config, dict) else {}
    if coverage.get("complete") is not True:
        issues.append("Authenticated loaded native configuration coverage is incomplete.")
    observed_at = _parse_timestamp(observed.get("observedAt"))
    if observed_at and observed_at < datetime.now(timezone.utc) - timedelta(days=1):
        issues.append("Current authenticated lifecycle source is stale.")
    return issues


def _build_source_bundle(store: StoreProtocol) -> dict[str, Any]:
    from integration.collect_managed_registry import _build_observed, _director_sources, _remote_config

    raw, inventory, workloads = asyncio.run(_director_sources())
    native_config = _remote_config()
    retired = ManagedRegistryRepository(store).read_retired_assignments() if getattr(store, "configured", False) else []
    observed = _build_observed(raw, inventory, workloads, native_config, retired)
    monitoring = store.load() if getattr(store, "configured", False) else None
    return {
        "observed": observed,
        "nativeConfig": native_config,
        "inventory": inventory,
        "monitoringSnapshot": monitoring,
    }


class ProductionLifecycleCollectors:
    def __init__(
        self,
        store: StoreProtocol | None = None,
        registry: RegistryProtocol | None = None,
        *,
        source_bundle_provider: Callable[[], dict[str, Any]] | None = None,
        retention_provider: Callable[[str, dict[str, Any] | None], dict[str, Any]] | None = None,
    ):
        self.store = store or Store()
        self.registry = registry or ManagedRegistryRepository(self.store)
        self._source_bundle_provider = source_bundle_provider or (lambda: _build_source_bundle(self.store))
        self._retention_provider = retention_provider or (lambda job_name, snapshot: _retained_recovery(snapshot, job_name))

    def _bundle(self) -> dict[str, Any]:
        bundle = self._source_bundle_provider()
        if not isinstance(bundle, dict):
            raise ValueError("Lifecycle collector source bundle must be a dictionary.")
        return bundle

    def _base(self, job_name: str) -> dict[str, Any]:
        bundle = self._bundle()
        observed = deepcopy(bundle.get("observed") or {})
        native_config = deepcopy(bundle.get("nativeConfig") or {})
        inventory = deepcopy(bundle.get("inventory") or {})
        monitoring = deepcopy(bundle.get("monitoringSnapshot") or {})
        assignment = self.registry.assignment_detail(job_name)
        proof = self.registry.proof_snapshot(job_name)
        entries = self.registry.enumerate_entries()
        retired = self.registry.read_retired_assignments()
        current = next((row for row in observed.get("jobs", []) if isinstance(row, dict) and row.get("jobName") == job_name), None)
        revision = int((assignment or {}).get("policy_revision") or 0)
        return {
            "bundle": bundle,
            "observed": observed,
            "nativeConfig": native_config,
            "inventory": inventory,
            "monitoring": monitoring,
            "assignment": assignment,
            "proof": proof,
            "entries": entries,
            "retired": retired,
            "current": current,
            "revision": revision if revision > 0 else None,
            "issues": _global_source_issues(observed, native_config),
        }

    def collect_clone_review(self, source_job_name: str, new_job_name: str, new_vm_uuid: str | None, repository_id: str | None, trusted_role: str) -> CloneCollected:
        data = self._base(source_job_name)
        proof_revision = data["revision"]
        names, resources, namespace_issues = _native_namespace(data["nativeConfig"], proof_revision)
        source_assignment = None
        snapshot: dict[str, Any] = {"job_name": source_job_name}
        evidence: dict[str, Any] = {
            "proof_revision": proof_revision or 0,
            "proof_coverage": list(_CLONE_COVERAGE),
            "existing_job_names": names,
            "existing_assignments": [],
            "resources": resources,
            "operations": [],
            "dependencies": [],
            "unresolved_intents": [],
            "repositories": _repository_options(data["nativeConfig"], data["observed"]),
            "source_assignment": {},
        }
        duplicate_protection: dict[str, Any] = {"sourceJobName": source_job_name, "newJobName": new_job_name}
        resource_ownership: list[dict[str, Any]] = []
        unsupported_changes = sorted(set(data["issues"] + [item["summary"] for item in namespace_issues]))

        if data["assignment"] and data["proof"] and data["revision"]:
            source_assignment = {
                "vm_identity": data["assignment"]["instance_uuid"],
                "stable_id": data["proof"]["stableId"],
                "job_name": data["assignment"]["job_name"],
                "repository_id": data["assignment"]["storage_name"],
                "state": "managed",
            }
            snapshot = {
                "stable_id": data["proof"]["stableId"],
                "job_name": source_job_name,
                "selection_revision": data["revision"],
                "snapshot_revision": data["revision"],
                "identity_revision": data["revision"],
                "managed_vm_ids": [data["assignment"]["instance_uuid"]],
                "repository_id": data["assignment"]["storage_name"],
            }
            evidence["source_assignment"] = source_assignment
        else:
            unsupported_changes.append("Managed registry does not yet contain a complete current source assignment for this job.")
            for key in ("assignments", "dependencies", "resources"):
                if key in evidence["proof_coverage"]:
                    evidence["proof_coverage"].remove(key)

        resource_use = ((data["proof"] or {}).get("resourceUse") or {}) if isinstance(data["proof"], dict) else {}
        if data["proof"]:
            for resource_type, name in (
                ("job", source_job_name),
                ("fileset", data["proof"].get("filesetName")),
                ("pool", data["proof"].get("poolName")),
                ("schedule", data["proof"].get("scheduleName")),
            ):
                if name:
                    usage = resource_use.get(resource_type if resource_type != "schedule" else "schedule", {})
                    resource_ownership.append(
                        {
                            "resourceType": resource_type,
                            "resourceName": name,
                            "ownership": _ownership(usage),
                            "usageCount": int(usage.get("usageCount") or 0),
                            "owners": list(usage.get("owners") or []),
                            "accounted": bool(usage.get("accounted")),
                        }
                    )
        if data["current"] and data["proof"]:
            current = data["current"]
            if current.get("instanceUuid") != data["assignment"]["instance_uuid"] or current.get("repositoryId") != data["assignment"]["storage_name"]:
                unsupported_changes.append("Current authenticated source identity no longer matches the managed registry assignment.")
                evidence["unresolved_intents"].append(_intent("other", "Current source identity drifted from the managed registry assignment.", proof_revision))
            if current.get("resourceIssues"):
                for item in current["resourceIssues"]:
                    unsupported_changes.append(str(item.get("summary")))
                if "resources" in evidence["proof_coverage"]:
                    evidence["proof_coverage"].remove("resources")
            deps = current.get("dependencies") if isinstance(current.get("dependencies"), list) else []
            evidence["dependencies"] = [
                _dependency(row.get("relation"), row.get("relatedStableId"), row.get("jobName"), proof_revision)
                for row in deps
                if isinstance(row, dict)
            ]
            if any(not row.get("jobName") for row in deps if isinstance(row, dict)) or any(
                row.get("related_job_name") == "Unknown" or row.get("related_stable_id") == "unknown" for row in evidence["dependencies"]
            ):
                evidence["unresolved_intents"].append(_intent("other", "Dependency proof is partial and cannot be treated as authoritative.", proof_revision))
            runtime_ops = [_normalize_operation(row) for row in self.store.lifecycle_operations(source_job_name)]
            monitoring = data["monitoring"] if isinstance(data["monitoring"], dict) else {}
            for row in monitoring.get("sessions", []) if isinstance(monitoring.get("sessions"), list) else []:
                if isinstance(row, dict) and _is_runtime_nonterminal(row, source_job_name):
                    runtime_state = "unknown" if str(row.get("status") or row.get("jobstatus") or "").lower() == "unknown" else "active"
                    runtime_ops.append(
                        {
                            "operation_id": str(row.get("sourceJobId") or row.get("jobId") or row.get("id") or "runtime"),
                            "kind": "backup",
                            "state": runtime_state,
                            "summary": f"Director session for {source_job_name} is still {runtime_state}.",
                        }
                    )
            evidence["operations"] = runtime_ops
            for op in runtime_ops:
                if op["state"] in {"active", "waiting", "prepared", "dispatching", "unknown"}:
                    evidence["unresolved_intents"].append(_intent("other", op["summary"], proof_revision))
            if current.get("sourceCoverage") and not all(current["sourceCoverage"].get(name) is True for name in ("director", "inventory", "config")):
                unsupported_changes.append("Current authenticated source coverage is partial for this job.")
        else:
            evidence["unresolved_intents"].append(_intent("other", "Current authenticated managed job evidence is unavailable.", proof_revision))

        evidence["existing_assignments"] = [
            {
                "vm_identity": row["instance_uuid"],
                "stable_id": row["stable_id"],
                "job_name": row["job_name"],
                "state": "managed",
            }
            for row in data["entries"]
            if row.get("instance_uuid") and row.get("stable_id") and row.get("job_name")
        ]
        released_staging_filtered = len(data["retired"]) == 0
        duplicate_protection["managedAssignments"] = len(evidence["existing_assignments"])
        duplicate_protection["releasedStagingFiltered"] = released_staging_filtered
        duplicate_protection["retiredConflicts"] = [
            row for row in data["retired"] if row.get("jobName") == source_job_name or row.get("instanceUuid") == new_vm_uuid
        ]
        if duplicate_protection["retiredConflicts"]:
            evidence["unresolved_intents"].append(_intent("other", "Unverified retired evidence conflicts with the requested clone target.", proof_revision))

        target_matches, target_state = _target_vm_state(data["inventory"], new_vm_uuid)
        duplicate_protection["targetVm"] = target_state
        if target_state["matchCount"] != 1 or target_state["visible"] is not True:
            if "target_vm" in evidence["proof_coverage"]:
                evidence["proof_coverage"].remove("target_vm")
        supported_repo = next((row for row in evidence["repositories"] if row["id"] == repository_id), None)
        duplicate_protection["targetRepository"] = {"id": repository_id, "supported": bool(supported_repo and supported_repo["supported"])}
        if not supported_repo:
            if "target_repository" in evidence["proof_coverage"]:
                evidence["proof_coverage"].remove("target_repository")

        if namespace_issues:
            if "names" in evidence["proof_coverage"]:
                evidence["proof_coverage"].remove("names")
        if unsupported_changes:
            evidence["unresolved_intents"].append(_intent("other", unsupported_changes[0], proof_revision))
        evidence["proof_coverage"] = [name for name in _CLONE_COVERAGE if name in evidence["proof_coverage"]]
        return {
            "snapshot": snapshot,
            "registryEvidence": evidence,
            "resourceOwnership": resource_ownership,
            "duplicateProtection": duplicate_protection,
            "unsupportedChanges": sorted(dict.fromkeys(unsupported_changes))[:8],
        }

    def collect_retirement_proof(self, job_name: str, trusted_role: str) -> RetirementProof:
        data = self._base(job_name)
        proof: RetirementProof = {
            "jobName": job_name,
            "stableId": (data["proof"] or {}).get("stableId"),
            "vmInstanceUuid": (data["assignment"] or {}).get("instance_uuid"),
            "repositoryId": (data["assignment"] or {}).get("storage_name"),
            "proofRevision": data["revision"] or 0,
            "jobRevision": data["revision"] or 0,
            "stableVmRevision": data["revision"] or 0,
            "repositoryRevision": data["revision"] or 0,
            "configurationRevisionId": (data["assignment"] or {}).get("configuration_revision_id"),
            "resources": [],
            "operations": [],
            "dependencies": [],
            "runtime": {
                "jobConfigPath": None,
                "jobConfigDigest": None,
                "jobConfigOwned": False,
                "exactJobFile": False,
                "ownershipVerified": False,
                "hooksVerified": False,
                "runtimeReadbackVerified": False,
                "hookReferences": [],
            },
            "retainedRecovery": self._retention_provider(job_name, data["monitoring"]),
        }
        if not data["assignment"] or not data["proof"] or not data["current"] or not data["revision"]:
            return proof

        current = data["current"]
        resource_use = (data["proof"].get("resourceUse") or {}) if isinstance(data["proof"], dict) else {}
        for source_name, target_name in (
            ("job", job_name),
            ("fileset", data["proof"].get("filesetName")),
            ("pool", data["proof"].get("poolName")),
            ("storage", data["proof"].get("storageName")),
            ("schedule", data["proof"].get("scheduleName")),
        ):
            if not target_name:
                continue
            usage = resource_use.get(source_name, {})
            proof["resources"].append(
                {
                    "resourceType": source_name if source_name != "storage" else "storage",
                    "resourceName": target_name,
                    "ownership": _ownership(usage),
                    "usageCount": int(usage.get("usageCount") or 0),
                }
            )
        proof["operations"] = [_normalize_operation(row) for row in self.store.lifecycle_operations(job_name)]
        monitoring = data["monitoring"] if isinstance(data["monitoring"], dict) else {}
        for row in monitoring.get("sessions", []) if isinstance(monitoring.get("sessions"), list) else []:
            if isinstance(row, dict) and _is_runtime_nonterminal(row, job_name):
                proof["operations"].append(
                    {
                        "operation_id": str(row.get("sourceJobId") or row.get("jobId") or row.get("id") or "runtime"),
                        "kind": "restore" if str(row.get("type") or "").lower() in {"restore", "r"} else "backup",
                        "state": "unknown" if str(row.get("status") or row.get("jobstatus") or "").lower() == "unknown" else "active",
                        "summary": f"Director runtime for {job_name} is still active.",
                    }
                )
        deps = current.get("dependencies") if isinstance(current.get("dependencies"), list) else []
        proof["dependencies"] = [{"jobName": row.get("jobName"), "relation": row.get("relation")} for row in deps if isinstance(row, dict) and row.get("jobName")]
        partial_dependencies = any(isinstance(row, dict) and not row.get("jobName") for row in deps)
        proof["runtime"] = {
            "jobConfigPath": ((data["proof"].get("configPaths") or {}).get("jobConfigPath")),
            "jobConfigDigest": ((data["proof"].get("configDigests") or {}).get("jobConfigDigest")),
            "jobConfigOwned": _ownership(resource_use.get("job", {})) == "exclusive",
            "exactJobFile": bool((data["proof"].get("configPaths") or {}).get("jobConfigPath") and (data["proof"].get("configDigests") or {}).get("jobConfigDigest")),
            "ownershipVerified": (
                current.get("instanceUuid") == data["assignment"]["instance_uuid"]
                and current.get("repositoryId") == data["assignment"]["storage_name"]
                and all((current.get("sourceCoverage") or {}).get(name) is True for name in ("director", "inventory", "config"))
            ),
            "hooksVerified": not bool(data["issues"]) and not bool(current.get("resourceIssues")) and not partial_dependencies and all(row.get("jobName") for row in proof["dependencies"]),
            "runtimeReadbackVerified": (
                current.get("jobConfigDigest") == ((data["proof"].get("configDigests") or {}).get("jobConfigDigest"))
                and current.get("jobConfigPath") == ((data["proof"].get("configPaths") or {}).get("jobConfigPath"))
            ),
            "hookReferences": [row["jobName"] for row in proof["dependencies"]] + (["unknown-dependency"] if partial_dependencies else []),
        }
        retained = proof["retainedRecovery"]
        if not retained.get("latestJobIds"):
            retained["catalogVisibilityConfirmed"] = False
            retained["stableRecoveryReferencesConfirmed"] = False
        return proof


def collect_clone_review(source_job_name: str, new_job_name: str, new_vm_uuid: str | None, repository_id: str | None, trusted_role: str) -> CloneCollected:
    return ProductionLifecycleCollectors().collect_clone_review(source_job_name, new_job_name, new_vm_uuid, repository_id, trusted_role)


def collect_retirement_proof(job_name: str, trusted_role: str) -> RetirementProof:
    return ProductionLifecycleCollectors().collect_retirement_proof(job_name, trusted_role)
