"""Pure trusted-evidence normalizer for disable-schedule preview."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from backend.job_lifecycle import DisableSchedulePreviewRequest


_COVERAGE = {"operations", "dependencies", "intents", "resources"}


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _bounded(blockers: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for item in blockers:
        key = (item["code"], item["summary"])
        if key not in seen:
            seen.add(key)
            out.append(item)
        if len(out) == 8:
            break
    return out


def normalize_disable_evidence(evidence: dict, job_name: str) -> dict:
    """Return planner-compatible disable evidence or explicit bounded blockers."""
    proof_digest = _digest(evidence)
    if not isinstance(evidence, dict):
        return {"job_name": job_name, "proof_digest": proof_digest, "blockers": [_block("invalid_evidence", "Trusted collector evidence must be a dictionary.")]}
    blockers: list[dict[str, str]] = []
    collector = evidence.get("collector")
    exact_job = evidence.get("exact_job")
    registry = evidence.get("registry")
    trusted_role = evidence.get("trusted_role")
    if not isinstance(collector, dict) or collector.get("complete") is not True or (type(collector.get("revision")) is not int or not 1 <= collector["revision"] <= 1_000_000_000):
        blockers.append(_block("missing_collector_proof", "Collector completeness and revision are required."))
    if not isinstance(trusted_role, str) or trusted_role not in {"Admin", "Backup Operator", "Viewer"}:
        blockers.append(_block("missing_trusted_role", "Trusted actor role must be supplied by the server caller."))
    if not isinstance(exact_job, dict):
        blockers.append(_block("missing_exact_job", "Exact job proof is required."))
    if not isinstance(registry, dict):
        blockers.append(_block("missing_registry_proof", "Registry proof is required."))
    if blockers:
        return {"job_name": job_name, "proof_digest": proof_digest, "blockers": _bounded(blockers)}

    revision = collector["revision"]
    if collector.get("truncated") is True or registry.get("truncated") is True:
        blockers.append(_block("partial_registry", "Bounded or truncated collector results cannot prove complete activity coverage."))
    if exact_job.get("job_name") != job_name:
        blockers.append(_block("foreign_job", "Exact job proof does not bind to the requested managed job."))
    vm_uuid = exact_job.get("managed_vm_uuid")
    schedule = exact_job.get("schedule")
    required_job = {"stable_id", "job_name", "selection_revision", "snapshot_revision", "identity_revision", "repository_id", "managed_vm_uuid", "schedule"}
    if set(required_job) - set(exact_job):
        blockers.append(_block("partial_snapshot", "Exact job proof is missing stable identity, repository, VM UUID or schedule fields."))
    if any(type(exact_job.get(key)) is not int or exact_job[key] < 1 for key in ("selection_revision", "snapshot_revision", "identity_revision")):
        blockers.append(_block("invalid_revision", "Job identity revisions must be positive integers."))
    if exact_job.get("selection_revision") != revision or exact_job.get("snapshot_revision") != revision:
        blockers.append(_block("stale_snapshot", "Exact job proof must match the current collector revision."))
    if not isinstance(vm_uuid, str):
        blockers.append(_block("missing_vm_uuid", "Exact job proof must include one persisted VM UUID."))
    if isinstance(exact_job.get("managed_vm_uuids"), list):
        blockers.append(_block("unsupported_multi_vm", "Disable preview accepts exactly one persisted VM UUID."))
    if not isinstance(schedule, dict):
        blockers.append(_block("missing_schedule_proof", "Exact job proof must include the current schedule binding."))
    else:
        if schedule.get("ownership") != "exclusive" or type(schedule.get("usage_count")) is not int or schedule.get("usage_count") != 1:
            blockers.append(_block("shared_schedule", "Disable preview requires an exclusively owned schedule binding."))
        if schedule.get("proof_revision") != revision:
            blockers.append(_block("stale_schedule", "Schedule proof must match the current collector revision."))
        if not schedule.get("resource_name"):
            blockers.append(_block("missing_schedule_proof", "Schedule proof must include the bound schedule resource name."))

    coverage = registry.get("coverage")
    enumerated = registry.get("enumerated")
    if coverage != sorted(_COVERAGE):
        blockers.append(_block("partial_registry", "Registry coverage must explicitly include operations, dependencies, intents and resources."))
    if not isinstance(enumerated, dict) or any(enumerated.get(name) is not True for name in _COVERAGE):
        blockers.append(_block("partial_registry", "Registry enumeration flags must explicitly confirm complete operations, dependencies, intents and resources."))
    if registry.get("revision") != revision:
        blockers.append(_block("stale_registry_proof", "Registry proof must match the current collector revision."))
    if registry.get("job_name") != job_name or registry.get("stable_id") != exact_job.get("stable_id"):
        blockers.append(_block("foreign_registry", "Registry proof must bind to the same exact managed job identity."))
    if registry.get("repository_id") != exact_job.get("repository_id"):
        blockers.append(_block("cross_repository_mismatch", "Repository proof must match the persisted managed job repository."))
    for name in ("operations", "dependencies", "unresolved_intents", "resources"):
        if not isinstance(registry.get(name), list):
            blockers.append(_block("partial_registry", f"Registry must explicitly enumerate {name}."))
    if blockers:
        return {"job_name": job_name, "proof_digest": proof_digest, "blockers": _bounded(blockers)}

    resources = list(registry["resources"])
    if not any(
        isinstance(row, dict)
        and row.get("resource_type") == "schedule"
        and row.get("resource_name") == schedule["resource_name"]
        and row.get("ownership") == "exclusive"
        and row.get("usage_count") == 1
        and row.get("proof_revision") == revision
        for row in resources
    ):
        return {"job_name": job_name, "proof_digest": proof_digest, "blockers": [_block("missing_resource_proof", "Registry does not confirm the exact exclusive schedule binding; ownership cannot be inferred.")]}
    normalized = {
        "job_name": job_name,
        "trusted_role": trusted_role,
        "proof_digest": proof_digest,
        "snapshot": {
            "stable_id": exact_job["stable_id"],
            "job_name": exact_job["job_name"],
            "selection_revision": exact_job["selection_revision"],
            "snapshot_revision": exact_job["snapshot_revision"],
            "identity_revision": exact_job["identity_revision"],
            "managed_vm_ids": [vm_uuid],
            "repository_id": exact_job["repository_id"],
        },
        "registry_evidence": {
            "proof_revision": revision,
            "proof_coverage": sorted(_COVERAGE),
            "resources": resources,
            "operations": registry["operations"],
            "dependencies": registry["dependencies"],
            "unresolved_intents": registry["unresolved_intents"],
        },
    }
    try:
        DisableSchedulePreviewRequest.model_validate({"actor_role": trusted_role, "snapshot": normalized["snapshot"], **normalized["registry_evidence"]})
    except (ValidationError, TypeError, ValueError):
        return {"job_name": job_name, "proof_digest": proof_digest, "blockers": [_block("invalid_evidence", "Collected evidence does not satisfy planner identity and registry bounds.")]}
    for row in [*resources, *registry["dependencies"], *registry["unresolved_intents"]]:
        if type(row.get("proof_revision")) is not int or row["proof_revision"] != revision:
            return {"job_name": job_name, "proof_digest": proof_digest, "blockers": [_block("stale_registry_proof", "All resource and dependency proofs must match the collected revision.")]}
    return normalized
