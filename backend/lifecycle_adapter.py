"""Fail-closed read-only adapter for disable-schedule preview evidence."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from backend.job_lifecycle import preview_disable_schedule

_REQUIRED_COVERAGE = {"operations", "dependencies", "intents", "resources"}
_SNAPSHOT_KEYS = {
    "stable_id",
    "job_name",
    "selection_revision",
    "snapshot_revision",
    "identity_revision",
    "managed_vm_ids",
    "repository_id",
}


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _blocker(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _impact(code: str, severity: str, summary: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "summary": summary}


def _finalize(job_name: str, blockers: list[dict[str, str]], impacts: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "jobName": job_name,
        "action": "disable_schedule",
        "executionSupported": False,
        "blockers": blockers[:8],
        "impacts": impacts[:8],
    }
    return {**payload, "digest": _digest(payload)}


def _normalize_snapshot(snapshot: dict[str, Any], requested_job: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    if not isinstance(snapshot, dict):
        return None, [_blocker("invalid_snapshot", "Snapshot evidence must be a dictionary.")]
    if snapshot.get("source_error"):
        return None, [_blocker("source_unavailable", "Snapshot source is unavailable; raw diagnostics are withheld.")]
    if snapshot.get("job_name") != requested_job:
        return None, [_blocker("job_not_found", f"Server snapshot does not prove managed job {requested_job}.")]
    missing = sorted(key for key in _SNAPSHOT_KEYS if key not in snapshot)
    if missing:
        return None, [_blocker("partial_snapshot", f"Snapshot is missing required fields: {', '.join(missing)}.")]
    if snapshot["selection_revision"] != snapshot["snapshot_revision"]:
        return None, [_blocker("stale_snapshot", "Snapshot revisions are not current and stable for review.")]
    return {
        "actor_role": snapshot.get("actor_role", "Viewer"),
        "snapshot": {key: snapshot[key] for key in _SNAPSHOT_KEYS},
    }, blockers


def _normalize_registry(registry_evidence: dict[str, Any] | None, snapshot_revision: int) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    blockers: list[dict[str, str]] = []
    if registry_evidence is None:
        return None, [_blocker("missing_registry_proof", "Registry evidence is required for disable preview.")]
    if not isinstance(registry_evidence, dict):
        return None, [_blocker("invalid_registry_evidence", "Registry evidence must be a dictionary.")]
    raw_coverage = registry_evidence.get("proof_coverage")
    if not isinstance(raw_coverage, list) or not all(isinstance(item, str) for item in raw_coverage):
        return None, [_blocker("invalid_registry_evidence", "Registry coverage must be an explicit list of proof categories.")]
    coverage = set(raw_coverage)
    for key in ("operations", "dependencies", "unresolved_intents"):
        if not isinstance(registry_evidence.get(key), list):
            blockers.append(_blocker("missing_registry_proof", f"Authoritative {key} evidence must be explicitly provided."))
    if coverage != _REQUIRED_COVERAGE:
        missing = sorted(_REQUIRED_COVERAGE - coverage)
        summary = "Registry coverage must explicitly include operations, dependencies, intents and resources."
        if missing:
            summary = f"{summary} Missing: {', '.join(missing)}."
        blockers.append(_blocker("missing_registry_proof", summary))
    if registry_evidence.get("proof_revision") != snapshot_revision:
        blockers.append(_blocker("stale_registry_proof", "Registry proof revision must match the current snapshot revision."))
    resources = registry_evidence.get("resources")
    if not isinstance(resources, list) or not resources:
        blockers.append(_blocker("missing_resource_bindings", "Registry evidence must include authoritative schedule resource bindings."))
    elif not any(isinstance(row, dict) and row.get("resource_type") == "schedule" for row in resources):
        blockers.append(_blocker("missing_resource_bindings", "Registry evidence must include a reviewed schedule resource entry."))
    if blockers:
        return None, blockers
    return {
        "proof_revision": registry_evidence["proof_revision"],
        "proof_coverage": sorted(coverage),
        "resources": resources,
        "operations": registry_evidence.get("operations", []),
        "dependencies": registry_evidence.get("dependencies", []),
        "unresolved_intents": registry_evidence.get("unresolved_intents", []),
    }, []


def build_disable_preview(
    snapshot: dict,
    job_name: str,
    *,
    trusted_role: str,
    registry_evidence: dict | None = None,
) -> dict:
    """Build a pure read-only disable preview from trusted server evidence only.

    Expected normalized inputs:
    - snapshot: planner-compatible keys plus optional source_error/actor_role
    - registry_evidence: proof_revision, proof_coverage, resources, operations,
      dependencies, unresolved_intents using planner-compatible field names
    """
    normalized_snapshot, blockers = _normalize_snapshot(snapshot, job_name)
    if blockers:
        return _finalize(job_name, blockers, [])
    normalized_registry, registry_blockers = _normalize_registry(
        registry_evidence, normalized_snapshot["snapshot"]["snapshot_revision"]
    )
    if registry_blockers:
        return _finalize(
            job_name,
            registry_blockers,
            [_impact("read_only_preview", "info", "Disable preview stays read-only until authoritative registry evidence is complete.")],
        )
    try:
        planner_result = preview_disable_schedule(
            {**normalized_snapshot, **normalized_registry},
            trusted_role=trusted_role,
        )
    except (ValidationError, TypeError, ValueError):
        return _finalize(job_name, [_blocker("invalid_evidence", "Evidence does not satisfy the reviewed planner contract.")], [])
    blockers = [
        {"code": item.code, "summary": item.summary}
        for item in planner_result.blockers
    ]
    impacts = [
        {"code": item.code, "severity": item.severity, "summary": item.summary}
        for item in planner_result.impacts
    ]
    return _finalize(job_name, blockers, impacts)
