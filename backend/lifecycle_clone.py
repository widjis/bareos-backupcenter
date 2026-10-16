"""Executable clone candidate service for managed lifecycle integration."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError

from backend.job_lifecycle import preview_clone_draft
from integration.onboarding_contract import build as build_onboarding_bundle

_REQUIRED_COVERAGE = {
    "operations",
    "dependencies",
    "intents",
    "resources",
    "names",
    "assignments",
    "target_vm",
    "target_repository",
}
_SNAPSHOT_KEYS = {
    "stable_id",
    "job_name",
    "selection_revision",
    "snapshot_revision",
    "identity_revision",
    "managed_vm_ids",
    "repository_id",
}
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$")


class CloneStoreTransaction(Protocol):
    def insert_intent(self, intent_id: str, record: dict[str, Any]) -> None: ...
    def update_intent(self, intent_id: str, record: dict[str, Any]) -> None: ...
    def read_intent(self, intent_id: str) -> dict[str, Any]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class CloneStore(Protocol):
    def get_intent(self, intent_id: str) -> dict[str, Any] | None: ...
    def begin(self) -> CloneStoreTransaction: ...


class CloneExecutor(Protocol):
    def apply_clone(self, native_candidate: dict[str, Any], *, actor: str, intent_id: str) -> dict[str, Any]: ...


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _impact(code: str, severity: str, summary: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "summary": summary}


def _native_candidate_digest(native_candidate: dict[str, Any] | None) -> str | None:
    return None if native_candidate is None else _digest(native_candidate)


def _review_digest(
    *,
    action: str,
    source_job_name: str,
    new_job_name: str,
    new_vm_uuid: str,
    target_repository_id: str,
    proof_revision: int,
    native_candidate: dict[str, Any] | None,
) -> str:
    return _digest(
        {
            "action": action,
            "sourceJobName": source_job_name,
            "newJobName": new_job_name,
            "newVmUuid": new_vm_uuid,
            "selectedRepositoryId": target_repository_id,
            "proofRevision": proof_revision,
            "nativeCandidateDigest": _native_candidate_digest(native_candidate),
        }
    )


def _finalize(
    source_job_name: str,
    new_job_name: str,
    new_vm_uuid: str,
    proof_revision: int,
    blockers: list[dict[str, str]],
    impacts: list[dict[str, str]],
    repository_options: list[dict[str, Any]],
    target_repository_id: str,
    native_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = "candidate_ready" if not blockers and native_candidate else "blocked"
    payload = {
        "jobName": source_job_name,
        "action": "clone_job",
        "readiness": readiness,
        "proofRevision": proof_revision,
        "blockers": blockers[:8],
        "impacts": impacts[:8],
        "summary": (
            "Clone creates a disabled manual candidate with dedicated native resources and no copied history."
            if readiness == "candidate_ready"
            else "Clone candidate is blocked until authoritative source identity, target repository and resource proof are complete."
        ),
        "executionSupported": readiness == "candidate_ready",
        "sourceJobName": source_job_name,
        "newJobName": new_job_name,
        "newVmUuid": new_vm_uuid,
        "selectedRepositoryId": target_repository_id,
        "repositoryOptions": repository_options,
        "nativeCandidate": native_candidate,
    }
    payload["reviewDigest"] = _review_digest(
        action=payload["action"],
        source_job_name=source_job_name,
        new_job_name=new_job_name,
        new_vm_uuid=new_vm_uuid,
        target_repository_id=target_repository_id,
        proof_revision=proof_revision,
        native_candidate=native_candidate,
    )
    return payload


def _normalize_snapshot(snapshot: dict[str, Any], source_job_name: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(snapshot, dict):
        return None, [_block("invalid_snapshot", "Clone snapshot evidence must be a dictionary.")]
    if snapshot.get("job_name") != source_job_name:
        return None, [_block("job_not_found", f"Exact managed source identity for {source_job_name} is unavailable.")]
    missing = sorted(key for key in _SNAPSHOT_KEYS if key not in snapshot)
    if missing:
        return None, [_block("partial_snapshot", f"Managed source proof is missing: {', '.join(missing)}.")]
    if snapshot["selection_revision"] != snapshot["snapshot_revision"]:
        return None, [_block("stale_snapshot", "Managed source snapshot is stale and must be reloaded before clone review.")]
    return {"actor_role": snapshot.get("actor_role", "Viewer"), "snapshot": {key: snapshot[key] for key in _SNAPSHOT_KEYS}}, []


def _normalize_registry(
    registry_evidence: dict[str, Any] | None,
    snapshot: dict[str, Any],
    new_job_name: str,
    new_vm_uuid: str,
    target_repository_id: str,
    copy_secrets: bool,
) -> tuple[dict[str, Any] | None, list[dict[str, str]], list[dict[str, Any]]]:
    if registry_evidence is None:
        return None, [_block("missing_registry_proof", "Complete authoritative registry evidence is required for clone review.")], []
    if not isinstance(registry_evidence, dict):
        return None, [_block("invalid_registry_evidence", "Clone registry evidence must be a dictionary.")], []
    coverage = set(registry_evidence.get("proof_coverage") or [])
    blockers: list[dict[str, str]] = []
    if coverage != _REQUIRED_COVERAGE:
        blockers.append(_block("missing_registry_proof", "Clone registry coverage must explicitly include lifecycle, namespace, assignment, VM and repository proof."))
    if registry_evidence.get("proof_revision") != snapshot["snapshot_revision"]:
        blockers.append(_block("stale_registry_proof", "Clone registry proof revision must match the current source snapshot revision."))
    for key in ("existing_job_names", "existing_assignments", "resources", "operations", "dependencies", "unresolved_intents", "repositories", "source_assignment"):
        if key not in registry_evidence:
            blockers.append(_block("invalid_registry_evidence", f"Clone registry evidence is missing {key}."))
    repository_options = []
    for row in registry_evidence.get("repositories", []):
        if not isinstance(row, dict):
            blockers.append(_block("invalid_registry_evidence", "Repository options must use the normalized dictionary contract."))
            continue
        repository_options.append(
            {
                "id": str(row.get("id", "")),
                "label": str(row.get("label", "")),
                "supported": bool(row.get("supported")),
            }
        )
    source_assignment = registry_evidence.get("source_assignment")
    if isinstance(source_assignment, dict):
        source_vm = snapshot["managed_vm_ids"][0] if snapshot.get("managed_vm_ids") else None
        if (
            source_assignment.get("stable_id") != snapshot["stable_id"]
            or source_assignment.get("job_name") != snapshot["job_name"]
            or str(source_assignment.get("vm_identity")) != str(source_vm)
            or source_assignment.get("repository_id") != snapshot["repository_id"]
        ):
            blockers.append(_block("foreign_key_mismatch", "Authoritative source assignment does not match the reviewed managed source identity."))
    selected_repo = next((row for row in repository_options if row["id"] == target_repository_id), None)
    if not selected_repo or not selected_repo["supported"]:
        blockers.append(_block("unsupported_repository", "Select a supported target repository option for clone generation."))
    if str(new_vm_uuid) == str(snapshot["managed_vm_ids"][0]):
        blockers.append(_block("same_vm_clone_unsupported", "Clone requires a distinct target VM UUID."))
    label = target_repository_id.removeprefix("repo-")
    if not _LABEL_RE.fullmatch(label) or new_job_name != f"VMware-{label}":
        blockers.append(_block("repository_name_mismatch", "Clone native generation currently requires target repository id repo-<Label> and new job name VMware-<Label>."))
    if copy_secrets:
        blockers.append(_block("secret_copy_unsupported", "Clone execution candidate never copies source secrets or transport credentials."))
    if blockers:
        return None, blockers, repository_options
    return {
        "proof_revision": registry_evidence["proof_revision"],
        "proof_coverage": sorted(coverage),
        "resources": registry_evidence["resources"],
        "operations": registry_evidence.get("operations", []),
        "dependencies": registry_evidence.get("dependencies", []),
        "unresolved_intents": registry_evidence.get("unresolved_intents", []),
        "existing_job_names": registry_evidence["existing_job_names"],
        "existing_assignments": registry_evidence["existing_assignments"],
        "new_job_name": new_job_name,
        "target_vm_identity": new_vm_uuid,
        "target_repository_id": target_repository_id,
        "requested_secret_copy": copy_secrets,
    }, [], repository_options


def _manualize_job(text: str) -> str:
    lines = []
    for raw in text.splitlines():
        if raw.strip().startswith("Schedule ="):
            continue
        if raw.strip() == "Enabled = yes":
            lines.append(" Enabled = no")
            continue
        lines.append(raw)
    return "\n".join(lines) + "\n"


def _build_native_candidate(new_vm_uuid: str, target_repository_id: str) -> dict[str, Any]:
    label = target_repository_id.removeprefix("repo-")
    bundle = build_onboarding_bundle(new_vm_uuid, label)
    files = dict(bundle["files"])
    job_path = f"bareos-dir.d/job/{label}.conf"
    files[job_path] = _manualize_job(files[job_path])
    resource_plan = {
        "job": bundle["job"],
        "fileset": bundle["fileset"],
        "pool": bundle["pool"],
        "storage": bundle["storage"],
        "folder": bundle["folder"],
        "files": files,
    }
    return {
        "automaticSchedule": False,
        "enabled": False,
        "historyCopied": False,
        "secretsCopied": False,
        "resourcePlan": resource_plan,
        "resourceDigest": _digest(resource_plan),
        "candidateDigest": _digest(
            {
                "automaticSchedule": False,
                "enabled": False,
                "historyCopied": False,
                "secretsCopied": False,
                "resourcePlan": resource_plan,
            }
        ),
    }


def review_clone_candidate(
    snapshot: dict,
    source_job_name: str,
    *,
    new_job_name: str,
    new_vm_uuid: str,
    target_repository_id: str,
    trusted_role: str,
    registry_evidence: dict | None,
    copy_secrets: bool = False,
) -> dict[str, Any]:
    proof_revision = 0
    normalized_snapshot, blockers = _normalize_snapshot(snapshot, source_job_name)
    if blockers:
        return _finalize(source_job_name, new_job_name, new_vm_uuid, proof_revision, blockers, [], [], target_repository_id)
    proof_revision = int(normalized_snapshot["snapshot"]["snapshot_revision"])
    normalized_registry, registry_blockers, repository_options = _normalize_registry(
        registry_evidence,
        normalized_snapshot["snapshot"],
        new_job_name,
        new_vm_uuid,
        target_repository_id,
        copy_secrets,
    )
    if registry_blockers:
        return _finalize(source_job_name, new_job_name, new_vm_uuid, proof_revision, registry_blockers, [], repository_options, target_repository_id)
    try:
        preview = preview_clone_draft(
            {**normalized_snapshot, **normalized_registry},
            trusted_role=trusted_role,
        )
    except (ValidationError, TypeError, ValueError):
        return _finalize(source_job_name, new_job_name, new_vm_uuid, proof_revision, [_block("invalid_evidence", "Clone evidence does not satisfy the reviewed planner contract.")], [], repository_options, target_repository_id)
    blockers = [{"code": row.code, "summary": row.summary} for row in preview.blockers]
    impacts = [{"code": row.code, "severity": row.severity, "summary": row.summary} for row in preview.impacts]
    native_candidate = None if blockers else _build_native_candidate(new_vm_uuid, target_repository_id)
    return _finalize(source_job_name, new_job_name, new_vm_uuid, proof_revision, blockers, impacts, repository_options, target_repository_id, native_candidate)


def apply_clone_candidate(
    review: dict[str, Any],
    *,
    actor: str,
    intent_id: str,
    expected_digest: str,
    store: CloneStore,
    executor: CloneExecutor,
) -> dict[str, Any]:
    if review.get("readiness") != "candidate_ready" or not review.get("executionSupported"):
        return review
    computed_digest = _review_digest(
        action=str(review.get("action", "")),
        source_job_name=str(review.get("sourceJobName", review.get("jobName", ""))),
        new_job_name=str(review.get("newJobName", "")),
        new_vm_uuid=str(review.get("newVmUuid", "")),
        target_repository_id=str(review.get("selectedRepositoryId", "")),
        proof_revision=int(review.get("proofRevision") or 0),
        native_candidate=review.get("nativeCandidate"),
    )
    if review.get("reviewDigest") != expected_digest or computed_digest != expected_digest:
        return {
            **review,
            "readiness": "blocked",
            "executionSupported": False,
            "blockers": [_block("review_digest_mismatch", "Clone apply requires a fresh approved review digest bound to the exact native candidate.")],
            "summary": "Clone apply is blocked until the caller supplies the current approved review digest.",
        }
    binding = {
        "actor": actor,
        "action": review["action"],
        "sourceJobName": review["sourceJobName"],
        "newJobName": review["newJobName"],
        "newVmUuid": review["newVmUuid"],
        "selectedRepositoryId": review["selectedRepositoryId"],
        "reviewDigest": expected_digest,
    }
    binding["intentBinding"] = _digest(binding)

    def conflict_response() -> dict[str, Any]:
        return {
            **review,
            "readiness": "blocked",
            "executionSupported": False,
            "blockers": [_block("idempotency_conflict", "This intent id is already bound to another actor, action, source, digest or target.")],
            "summary": "Clone apply is blocked until a fresh intent id is used for the new actor or review.",
        }

    def from_existing(existing: dict[str, Any] | None) -> dict[str, Any] | None:
        if not existing:
            return None
        if existing.get("intentBinding") != binding["intentBinding"]:
            return conflict_response()
        return existing["response"]

    existing = from_existing(store.get_intent(intent_id))
    if existing:
        return existing

    claim_response = {
        **review,
        "readiness": "dispatching",
        "executionSupported": False,
        "summary": "Clone dispatch claim is durable. Do not resend while this intent remains unresolved.",
        "executorState": "dispatching",
        "intentId": intent_id,
    }
    tx = store.begin()
    try:
        tx.insert_intent(
            intent_id,
            {
                "intentId": intent_id,
                **binding,
                "state": "Dispatching",
                "response": claim_response,
            },
        )
        tx.commit()
    except Exception:
        tx.rollback()
        existing = from_existing(store.get_intent(intent_id))
        if existing:
            return existing
        return {
            **review,
            "readiness": "blocked",
            "executionSupported": False,
            "blockers": [_block("claim_failed", "Clone apply could not persist a durable dispatch claim.")],
            "summary": "Clone apply did not start because the dispatch claim was not durably recorded.",
        }
    state = "unknown"
    summary = "Clone dispatch started but the final outcome is unresolved. Do not resend with the same intent."
    try:
        outcome = executor.apply_clone(review["nativeCandidate"], actor=actor, intent_id=intent_id)
        state = str(outcome.get("state", "")).lower()
        if state not in {"applied", "unknown"}:
            raise ValueError("Clone executor returned an unsupported state.")
        summary = outcome.get("summary") or (
            "Clone candidate was written to the target integration executor."
            if state == "applied"
            else "Clone candidate outcome is unknown; do not resend with the same intent."
        )
    except Exception:
        state = "unknown"
    final_response = {
        **review,
        "readiness": "completed" if state == "applied" else "unknown",
        "executionSupported": False,
        "summary": summary,
        "executorState": state,
        "intentId": intent_id,
    }
    finalize = store.begin()
    try:
        finalize.update_intent(
            intent_id,
            {
                "intentId": intent_id,
                **binding,
                "state": state.title(),
                "response": final_response,
            },
        )
        readback = finalize.read_intent(intent_id)
        finalize.commit()
        return readback["response"]
    except Exception:
        finalize.rollback()
        existing = from_existing(store.get_intent(intent_id))
        if existing:
            return existing
        return claim_response
