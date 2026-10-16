"""Authoritative job-retirement execution candidate with durable before-delete recording."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

_NONTERMINAL = {"Prepared", "Dispatching", "Accepted", "Running", "Waiting", "Unknown", "active", "waiting", "unknown"}
_TOP = {
    "jobName",
    "stableId",
    "vmInstanceUuid",
    "repositoryId",
    "proofRevision",
    "jobRevision",
    "stableVmRevision",
    "repositoryRevision",
    "configurationRevisionId",
    "resources",
    "operations",
    "dependencies",
    "runtime",
    "retainedRecovery",
}
_RUNTIME = {"jobConfigPath", "jobConfigDigest", "jobConfigOwned", "exactJobFile", "ownershipVerified", "hooksVerified", "runtimeReadbackVerified", "hookReferences"}
_RECOVERY = {"recoveryPointCount", "latestJobIds", "catalogReferenceIds", "catalogVisibilityConfirmed", "stableRecoveryReferencesConfirmed", "retentionOwnerConfirmed", "cleanupOwnerConfirmed", "mediaReadableVerified"}


class DurableRetirementStore(Protocol):
    def load_retirement_operation(self, idempotency_key: str) -> dict[str, Any] | None: ...
    def create_retirement_operation(self, intent: dict[str, Any]) -> dict[str, Any]: ...
    def save_retirement_record(self, operation_id: str, record: dict[str, Any]) -> dict[str, Any]: ...
    def finalize_retirement_operation(self, operation_id: str, state: str, result: dict[str, Any]) -> dict[str, Any]: ...
    def load_retirement_record(self, job_name: str) -> dict[str, Any] | None: ...


class RetirementConfigExecutor(Protocol):
    def capture_job_config(self, job_name: str) -> dict[str, Any]: ...
    def delete_job_config(self, job_name: str, *, expected_path: str, expected_digest: str) -> dict[str, Any]: ...
    def read_job_config(self, job_name: str) -> dict[str, Any]: ...
    def restore_job_config(self, beforeimage: dict[str, Any]) -> dict[str, Any]: ...


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _impact(code: str, severity: str, summary: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "summary": summary}


def _unique(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for item in items:
        key = (item["code"], item["summary"])
        if key not in seen:
            seen.add(key)
            rows.append(item)
    return rows


def _obligations() -> list[str]:
    return [
        "Backup data, Catalog history, volumes and file metadata remain preserved by this action.",
        "Retention and cleanup ownership stay explicit after retirement.",
        "Media readability and restore success require independent proof.",
    ]


def _contract(proof: dict[str, Any], blockers: list[dict[str, str]], readiness: str, execution_supported: bool) -> dict[str, Any]:
    retained = proof.get("retainedRecovery") or {}
    record = {
        "jobName": proof.get("jobName"),
        "stableId": proof.get("stableId"),
        "vmInstanceUuid": proof.get("vmInstanceUuid"),
        "repositoryId": proof.get("repositoryId"),
        "configurationRevisionId": proof.get("configurationRevisionId"),
        "proofRevision": proof.get("proofRevision", 0),
        "recordBeforeDelete": True,
    }
    impacts = [
        _impact("job_config_only", "warning", "Only the exact owned job configuration is removed; FileSet, Pool, Storage, Schedule, Catalog and volume data stay unchanged."),
        _impact("backups_preserved", "warning", "Backup data and retained recovery references remain preserved."),
        _impact("cleanup_retention_remain", "obligation", "Retention and cleanup duties remain in force after retirement."),
    ]
    if not retained.get("mediaReadableVerified"):
        impacts.append(_impact("media_readability_unverified", "info", "Media readability is not claimed by this retirement service without separate proof."))
    payload = {
        "jobName": proof.get("jobName"),
        "action": "remove_configuration",
        "readiness": readiness,
        "reviewDigest": _digest(
            {
                "action": "remove_configuration",
                "jobName": proof.get("jobName"),
                "proofRevision": proof.get("proofRevision", 0),
                "jobRevision": proof.get("jobRevision"),
                "stableVmRevision": proof.get("stableVmRevision"),
                "repositoryRevision": proof.get("repositoryRevision"),
                "configurationRevisionId": proof.get("configurationRevisionId"),
                "stableId": proof.get("stableId"),
                "repositoryId": proof.get("repositoryId"),
                "runtime": proof.get("runtime"),
                "retainedRecovery": proof.get("retainedRecovery"),
            }
        ),
        "proofRevision": proof.get("proofRevision", 0),
        "blockers": _unique(blockers)[:8],
        "impacts": _unique(impacts)[:8],
        "summary": "Remove only the exact owned job configuration while preserving backup data and stable recovery references.",
        "executionSupported": bool(execution_supported and not blockers),
        "preserveBackupData": True,
        "retirementRecord": record,
        "retainedRecovery": {
            "recoveryPointCount": retained.get("recoveryPointCount", 0),
            "latestJobIds": list(retained.get("latestJobIds", [])),
            "catalogReferenceIds": list(retained.get("catalogReferenceIds", [])),
            "mediaReadableVerified": bool(retained.get("mediaReadableVerified", False)),
            "restoreVerified": False,
        },
        "retainedObligations": _obligations(),
    }
    return payload


def review_retirement(proof: dict[str, Any], *, execution_supported: bool = True) -> dict[str, Any]:
    blockers: list[dict[str, str]] = []
    if not isinstance(proof, dict):
        return _contract({}, [_block("incomplete_proof", "Authoritative retirement proof is required.")], "blocked", False)
    missing = sorted(_TOP - set(proof))
    if missing:
        blockers.append(_block("incomplete_proof", f"Authoritative proof is missing fields: {', '.join(missing)}."))
    runtime = proof.get("runtime") if isinstance(proof.get("runtime"), dict) else {}
    retained = proof.get("retainedRecovery") if isinstance(proof.get("retainedRecovery"), dict) else {}
    if runtime and (miss := sorted(_RUNTIME - set(runtime))):
        blockers.append(_block("incomplete_proof", f"Runtime proof is missing fields: {', '.join(miss)}."))
    if retained and (miss := sorted(_RECOVERY - set(retained))):
        blockers.append(_block("incomplete_proof", f"Retained recovery proof is missing fields: {', '.join(miss)}."))
    resources = proof.get("resources") if isinstance(proof.get("resources"), list) else []
    resource_types = {row.get("resourceType") for row in resources if isinstance(row, dict)}
    if {"job", "fileset", "pool", "storage"} - resource_types:
        blockers.append(_block("incomplete_proof", "Ownership proof must include job, fileset, pool and storage resources."))
    jobs = [row for row in resources if isinstance(row, dict) and row.get("resourceType") == "job"]
    if len(jobs) != 1 or jobs[0].get("ownership") != "exclusive" or jobs[0].get("usageCount") != 1:
        blockers.append(_block("shared_job_file", "Job removal requires one exact owned job configuration resource."))
    if runtime and (not runtime.get("jobConfigOwned") or not runtime.get("exactJobFile") or not runtime.get("ownershipVerified")):
        blockers.append(_block("shared_job_file", "Runtime ownership proof does not confirm one exact owned job configuration file."))
    if runtime and (not runtime.get("hooksVerified") or not runtime.get("runtimeReadbackVerified")):
        blockers.append(_block("incomplete_proof", "Hook and runtime readback proof must be complete before retirement."))
    if runtime and runtime.get("hookReferences"):
        blockers.append(_block("hook_blocker", "Managed hooks still reference this job; remove those references before retirement."))
    for row in proof.get("operations", []):
        if isinstance(row, dict) and str(row.get("state")) in _NONTERMINAL:
            blockers.append(_block("unresolved_operation", f"Operation {row.get('kind', 'unknown')} is still {row.get('state', 'unknown')}."))
    if proof.get("dependencies"):
        blockers.append(_block("dependency_blocker", "Dependent jobs must be resolved before removing this job configuration."))
    if retained and (
        not retained.get("catalogVisibilityConfirmed")
        or not retained.get("stableRecoveryReferencesConfirmed")
        or not retained.get("retentionOwnerConfirmed")
        or not retained.get("cleanupOwnerConfirmed")
    ):
        blockers.append(_block("incomplete_proof", "Retained recovery, Catalog visibility, retention and cleanup proof must all be complete."))
    return _contract(proof, blockers, "candidate_ready" if not blockers else "blocked", execution_supported)


def execute_retirement(
    store: DurableRetirementStore,
    executor: RetirementConfigExecutor,
    proof: dict[str, Any],
    *,
    actor: str,
    idempotency_key: str,
    review_digest: str,
    proof_revision: int,
) -> dict[str, Any]:
    review = review_retirement(proof)
    if review["readiness"] != "candidate_ready":
        raise ValueError("Retirement proof is not ready for execution.")
    if not actor:
        raise ValueError("Actor is required.")
    if review["reviewDigest"] != review_digest or review["proofRevision"] != proof_revision:
        raise ValueError("Retirement proof drifted since review.")
    existing = store.load_retirement_operation(idempotency_key)
    if existing:
        intent = existing.get("intent", {})
        if intent.get("actor") != actor or intent.get("jobName") != proof["jobName"] or intent.get("reviewDigest") != review_digest:
            raise ValueError("Request key belongs to another retirement intent.")
        return existing["result"]
    before = executor.capture_job_config(proof["jobName"])
    runtime = proof["runtime"]
    if (
        before.get("path") != runtime["jobConfigPath"]
        or before.get("digest") != runtime["jobConfigDigest"]
        or not before.get("exists")
    ):
        raise ValueError("Retirement proof drifted since review.")
    operation = store.create_retirement_operation(
        {
            "id": str(uuid4()),
            "actor": actor,
            "idempotencyKey": idempotency_key,
            "jobName": proof["jobName"],
            "reviewDigest": review_digest,
            "proofRevision": proof_revision,
        }
    )
    record = {
        "state": "Prepared",
        "retiredAt": None,
        "operationId": operation["id"],
        "jobName": proof["jobName"],
        "stableId": proof["stableId"],
        "vmInstanceUuid": proof["vmInstanceUuid"],
        "repositoryId": proof["repositoryId"],
        "configurationRevisionId": proof["configurationRevisionId"],
        "proofRevision": proof["proofRevision"],
        "jobRevision": proof["jobRevision"],
        "stableVmRevision": proof["stableVmRevision"],
        "repositoryRevision": proof["repositoryRevision"],
        "beforeImage": before,
        "retainedRecovery": review["retainedRecovery"],
        "retainedObligations": review["retainedObligations"],
    }
    store.save_retirement_record(operation["id"], record)
    try:
        delete_receipt = executor.delete_job_config(
            proof["jobName"],
            expected_path=runtime["jobConfigPath"],
            expected_digest=runtime["jobConfigDigest"],
        )
        readback = executor.read_job_config(proof["jobName"])
        if readback.get("exists"):
            raise RuntimeError("Job configuration is still present after removal.")
        applied_at = datetime.now(timezone.utc).isoformat()
        result = {
            **review,
            "readiness": "applied",
            "summary": "Retirement record persisted before deletion; the exact owned job configuration was removed and retained recovery references remain discoverable.",
            "retirementRecord": {
                **review["retirementRecord"],
                "state": "Applied",
                "operationId": operation["id"],
                "retiredAt": applied_at,
                "beforeImageDigest": before["digest"],
                "jobConfigPath": before["path"],
                "deleteReceipt": delete_receipt,
            },
        }
        store.finalize_retirement_operation(operation["id"], "Applied", result)
        return result
    except Exception as exc:
        try:
            executor.restore_job_config(before)
            restored = executor.read_job_config(proof["jobName"])
            if not restored.get("exists") or restored.get("digest") != before["digest"]:
                raise RuntimeError("Rollback readback did not restore the original job configuration.")
            failed = {
                **review,
                "readiness": "failed",
                "executionSupported": False,
                "summary": "Retirement apply failed and the original job configuration was restored.",
                "retirementRecord": {
                    **review["retirementRecord"],
                    "state": "Failed",
                    "operationId": operation["id"],
                    "beforeImageDigest": before["digest"],
                    "jobConfigPath": before["path"],
                },
            }
            store.finalize_retirement_operation(operation["id"], "Failed", failed)
            return failed
        except Exception:
            unknown = {
                **review,
                "readiness": "unknown",
                "executionSupported": False,
                "summary": "Retirement outcome is unknown. The before-image receipt is durable; reconcile the job file and retirement record before another request. No resend is allowed.",
                "blockers": _unique(review["blockers"] + [_block("unknown_outcome", str(exc))])[:8],
                "retirementRecord": {
                    **review["retirementRecord"],
                    "state": "Unknown",
                    "operationId": operation["id"],
                    "beforeImageDigest": before["digest"],
                    "jobConfigPath": before["path"],
                },
            }
            store.finalize_retirement_operation(operation["id"], "Unknown", unknown)
            return unknown


def retired_job_discovery(store: DurableRetirementStore, job_name: str) -> dict[str, Any] | None:
    record = store.load_retirement_record(job_name)
    if not record or record.get("state") != "Applied":
        return None
    retained = record["retainedRecovery"]
    return {
        "jobName": record["jobName"],
        "stableId": record["stableId"],
        "vmInstanceUuid": record["vmInstanceUuid"],
        "repositoryId": record["repositoryId"],
        "preserveBackupData": True,
        "retirementRecord": {
            "state": record["state"],
            "operationId": record["operationId"],
            "configurationRevisionId": record["configurationRevisionId"],
            "proofRevision": record["proofRevision"],
            "retiredAt": record["retiredAt"],
        },
        "retainedRecovery": {
            "recoveryPointCount": retained["recoveryPointCount"],
            "latestJobIds": list(retained["latestJobIds"]),
            "catalogReferenceIds": list(retained["catalogReferenceIds"]),
            "mediaReadableVerified": bool(retained.get("mediaReadableVerified", False)),
            "restoreVerified": False,
        },
        "retainedObligations": list(record["retainedObligations"]),
    }
