"""APIRouter for clone/remove lifecycle endpoints with server-owned dependency injection only.

Expected gateway object from ``get_gateway``:
- ``store``: durable server-owned store. Clone apply needs ``get_intent()``, ``begin()``,
  and ``actor_allowed(username, kind)``. Remove apply/discovery also needs the
  ``backend.lifecycle_retirement.DurableRetirementStore`` methods.
- ``lifecycle_clone_collector`` with
  ``collect_clone_review(source_job_name, new_job_name, new_vm_uuid, repository_id, trusted_role)``.
  It must return authoritative server-owned inputs:
  ``snapshot``, ``registryEvidence`` and optional ``resourceOwnership``,
  ``duplicateProtection``, ``unsupportedChanges``.
- ``lifecycle_retirement_collector`` with
  ``collect_retirement_proof(job_name, trusted_role)`` returning full authoritative proof.
- ``lifecycle_clone_executor`` implementing ``backend.lifecycle_clone.CloneExecutor``.
- ``lifecycle_retirement_executor`` implementing
  ``backend.lifecycle_retirement.RetirementConfigExecutor``.
- ``lifecycle_extra_readiness`` dict with explicit booleans:
  ``installedReady``, ``transportReady``, ``collectorReady``, ``durableStoreReady``,
  ``executorReady``. Missing keys are treated as not ready.

This module never accepts proof flags/evidence from the browser and never fabricates
authoritative lifecycle proof. When prerequisites or collectors are absent, review
endpoints return HTTP 200 blocked contracts with proofRevision 0; apply endpoints
return HTTP 409 and do not write.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field


_ALLOWED_ORIGINS = {"http://127.0.0.1:3000", "http://localhost:3000"}
_READINESS_KEYS = (
    ("installedReady", "missing_installed_prerequisite", "Installed lifecycle candidate is not confirmed ready on this server."),
    ("transportReady", "missing_transport_prerequisite", "Lifecycle transport is not available for this action."),
    ("collectorReady", "missing_collector_prerequisite", "Authoritative lifecycle collector is not available."),
    ("durableStoreReady", "missing_durable_store_prerequisite", "Durable lifecycle store is not available."),
    ("executorReady", "missing_executor_prerequisite", "Lifecycle executor is not available."),
)


class CloneReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source_job_name: str = Field(alias="sourceJobName", pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    new_job_name: str = Field(alias="newJobName", pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    new_vm_uuid: str | None = Field(default=None, alias="newVmUuid", pattern=r"^[0-9A-Fa-f-]{36}$")
    repository_id: str | None = Field(default=None, alias="repositoryId", pattern=r"^[A-Za-z0-9_.:-]{1,128}$")


class CloneApplyRequest(CloneReviewRequest):
    idempotency_key: UUID = Field(alias="idempotencyKey")
    review_digest: str = Field(alias="reviewDigest", pattern=r"^[0-9a-f]{64}$")
    proof_revision: int = Field(alias="proofRevision", ge=1, le=1_000_000_000)
    confirmed: bool = Field(default=False)


class RetirementReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    job_name: str = Field(alias="jobName", pattern=r"^[A-Za-z0-9_.-]{1,128}$")


class RetirementApplyRequest(RetirementReviewRequest):
    idempotency_key: UUID = Field(alias="idempotencyKey")
    review_digest: str = Field(alias="reviewDigest", pattern=r"^[0-9a-f]{64}$")
    proof_revision: int = Field(alias="proofRevision", ge=1, le=1_000_000_000)
    confirmed: bool = Field(default=False)


def _digest(payload: Any) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _impact(code: str, severity: str, summary: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "summary": summary}


def _require_admin(request: Request) -> None:
    if getattr(request.state, "user", {}).get("role") != "Admin":
        raise HTTPException(403, "Administrator permission required.")


def _require_confirmed_post(request: Request) -> None:
    if request.headers.get("origin") not in _ALLOWED_ORIGINS or request.headers.get("x-backup-center-action") != "confirmed":
        raise HTTPException(403, "A confirmed same-origin operation is required.")


def _actor_allowed(gateway: Any, username: str) -> bool:
    check = getattr(getattr(gateway, "store", None), "actor_allowed", None)
    return bool(callable(check) and check(username, "provision"))


def _prereq_blockers(gateway: Any) -> list[dict[str, str]]:
    readiness = getattr(gateway, "lifecycle_extra_readiness", {}) or {}
    blockers: list[dict[str, str]] = []
    for key, code, summary in _READINESS_KEYS:
        if readiness.get(key) is not True:
            blockers.append(_block(code, summary))
    return blockers


def _clone_blocked(
    body: CloneReviewRequest,
    blockers: list[dict[str, str]],
    *,
    repository_options: list[dict[str, Any]] | None = None,
    resource_ownership: list[dict[str, Any]] | None = None,
    duplicate_protection: dict[str, Any] | None = None,
    unsupported_changes: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "jobName": body.source_job_name,
        "action": "clone_job",
        "readiness": "blocked",
        "proofRevision": 0,
        "blockers": blockers[:8],
        "impacts": [_impact("clone_disabled", "info", "Clone review remains blocked until authoritative prerequisites and target selection are complete.")],
        "summary": "Clone review is blocked until the selected VM, repository and server-owned lifecycle prerequisites are available.",
        "executionSupported": False,
        "sourceJobName": body.source_job_name,
        "newJobName": body.new_job_name,
        "newVmUuid": body.new_vm_uuid,
        "selectedRepositoryId": body.repository_id,
        "draftPlan": None,
        "resourceOwnership": resource_ownership or [],
        "duplicateProtection": duplicate_protection or {},
        "unsupportedChanges": unsupported_changes or [],
        "repositoryOptions": repository_options or [],
    }
    payload["reviewDigest"] = _digest(payload)
    return payload


def _clone_contract(review: dict[str, Any], collected: dict[str, Any]) -> dict[str, Any]:
    candidate = review.get("nativeCandidate") or {}
    payload = {
        "jobName": review["jobName"],
        "action": review["action"],
        "readiness": review["readiness"],
        "reviewDigest": review["reviewDigest"],
        "proofRevision": review["proofRevision"],
        "blockers": review["blockers"],
        "impacts": review["impacts"],
        "summary": review["summary"],
        "executionSupported": review["executionSupported"],
        "sourceJobName": review["sourceJobName"],
        "newJobName": review["newJobName"],
        "newVmUuid": review["newVmUuid"],
        "selectedRepositoryId": review["selectedRepositoryId"],
        "draftPlan": candidate.get("resourcePlan"),
        "resourceOwnership": collected.get("resourceOwnership", []),
        "duplicateProtection": collected.get("duplicateProtection", {}),
        "unsupportedChanges": collected.get("unsupportedChanges", []),
        "repositoryOptions": review.get("repositoryOptions", []),
    }
    if "intentId" in review:
        payload["intentId"] = review["intentId"]
    if "executorState" in review:
        payload["executorState"] = review["executorState"]
    return payload


def _sanitize_review_failure(action: str, job_name: str, summary: str, *, new_job_name: str | None = None, new_vm_uuid: str | None = None, repository_id: str | None = None) -> dict[str, Any]:
    if action == "clone_job":
        body = CloneReviewRequest.model_validate({"sourceJobName": job_name, "newJobName": new_job_name or "", "newVmUuid": new_vm_uuid, "repositoryId": repository_id})
        return _clone_blocked(body, [_block("server_unavailable", summary)])
    return {
        "jobName": job_name,
        "action": "remove_configuration",
        "readiness": "blocked",
        "reviewDigest": _digest({"action": "remove_configuration", "jobName": job_name, "blockers": [summary]}),
        "proofRevision": 0,
        "blockers": [_block("server_unavailable", summary)],
        "impacts": [_impact("review_blocked", "info", "Removal review remains blocked until authoritative server-owned prerequisites are available.")],
        "summary": "Removal review is blocked until authoritative lifecycle prerequisites are available.",
        "executionSupported": False,
        "preserveBackupData": True,
        "retirementRecord": {"jobName": job_name, "proofRevision": 0, "recordBeforeDelete": True},
        "retainedRecovery": {"recoveryPointCount": 0, "latestJobIds": [], "catalogReferenceIds": [], "mediaReadableVerified": False, "restoreVerified": False},
        "retainedObligations": [],
    }


def _remove_blocked(job_name: str, blockers: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "jobName": job_name,
        "action": "remove_configuration",
        "readiness": "blocked",
        "proofRevision": 0,
        "blockers": blockers[:8],
        "impacts": [_impact("review_blocked", "info", "Removal review remains blocked until authoritative server-owned prerequisites are available.")],
        "summary": "Removal review is blocked until authoritative lifecycle prerequisites are available.",
        "executionSupported": False,
        "preserveBackupData": True,
        "retirementRecord": {"jobName": job_name, "proofRevision": 0, "recordBeforeDelete": True},
        "retainedRecovery": {"recoveryPointCount": 0, "latestJobIds": [], "catalogReferenceIds": [], "mediaReadableVerified": False, "restoreVerified": False},
        "retainedObligations": [],
    }
    payload["reviewDigest"] = _digest(payload)
    return payload


def _clone_review(gateway: Any, body: CloneReviewRequest, trusted_role: str) -> dict[str, Any]:
    blockers = _prereq_blockers(gateway)
    local_blockers: list[dict[str, str]] = []
    if not body.new_vm_uuid:
        local_blockers.append(_block("missing_selected_vm", "Select the target VM before reviewing a clone."))
    if not body.repository_id:
        local_blockers.append(_block("missing_repository", "Select the target repository before reviewing a clone."))
    collector = getattr(gateway, "lifecycle_clone_collector", None)
    if blockers or local_blockers or not hasattr(collector, "collect_clone_review"):
        if not hasattr(collector, "collect_clone_review"):
            blockers.append(_block("missing_collector_prerequisite", "Authoritative clone collector is not available."))
        return _clone_blocked(body, blockers + local_blockers)
    try:
        collected = collector.collect_clone_review(body.source_job_name, body.new_job_name, body.new_vm_uuid, body.repository_id, trusted_role)
        from backend.lifecycle_clone import review_clone_candidate

        review = review_clone_candidate(
            collected["snapshot"],
            body.source_job_name,
            new_job_name=body.new_job_name,
            new_vm_uuid=body.new_vm_uuid or "",
            target_repository_id=body.repository_id or "",
            trusted_role=trusted_role,
            registry_evidence=collected["registryEvidence"],
            copy_secrets=False,
        )
        return _clone_contract(review, collected)
    except Exception:
        return _clone_blocked(body, [_block("server_unavailable", "Clone review is unavailable from the authoritative server-owned collector.")])


def _remove_review(gateway: Any, job_name: str, trusted_role: str) -> dict[str, Any]:
    blockers = _prereq_blockers(gateway)
    collector = getattr(gateway, "lifecycle_retirement_collector", None)
    if blockers or not hasattr(collector, "collect_retirement_proof"):
        if not hasattr(collector, "collect_retirement_proof"):
            blockers.append(_block("missing_collector_prerequisite", "Authoritative removal collector is not available."))
        return _remove_blocked(job_name, blockers)
    try:
        proof = collector.collect_retirement_proof(job_name, trusted_role)
        from backend.lifecycle_retirement import review_retirement

        return review_retirement(proof, execution_supported=not _prereq_blockers(gateway))
    except Exception:
        return _sanitize_review_failure("remove_configuration", job_name, "Removal review is unavailable from the authoritative server-owned collector.")


def create_lifecycle_extra_router(get_gateway) -> APIRouter:
    router = APIRouter()

    @router.post("/api/jobs/lifecycle/clone/review")
    async def clone_review(body: CloneReviewRequest, request: Request):
        _require_admin(request)
        _require_confirmed_post(request)
        return _clone_review(get_gateway(), body, request.state.user["role"])

    @router.post("/api/jobs/lifecycle/clone", status_code=202)
    async def clone_apply(body: CloneApplyRequest, request: Request):
        _require_admin(request)
        _require_confirmed_post(request)
        if body.confirmed is not True:
            raise HTTPException(409, "Clone confirmation is required.")
        gateway = get_gateway()
        if _prereq_blockers(gateway):
            raise HTTPException(409, "Lifecycle clone prerequisites are not ready.")
        if not _actor_allowed(gateway, request.state.user["username"]):
            raise HTTPException(403, "Administrator permission was revoked.")
        review = _clone_review(
            gateway,
            CloneReviewRequest(
                sourceJobName=body.source_job_name,
                newJobName=body.new_job_name,
                newVmUuid=body.new_vm_uuid,
                repositoryId=body.repository_id,
            ),
            request.state.user["role"],
        )
        if review["proofRevision"] != body.proof_revision or review["reviewDigest"] != body.review_digest:
            raise HTTPException(409, "Clone review changed. Review again before apply.")
        if review["readiness"] != "candidate_ready" or not review["executionSupported"]:
            raise HTTPException(409, review["summary"])
        if not body.new_vm_uuid or not body.repository_id:
            raise HTTPException(409, "Clone target VM and repository are required before apply.")
        try:
            collected = gateway.lifecycle_clone_collector.collect_clone_review(body.source_job_name, body.new_job_name, body.new_vm_uuid, body.repository_id, request.state.user["role"])
            from backend.lifecycle_clone import apply_clone_candidate, review_clone_candidate

            internal_review = review_clone_candidate(
                collected["snapshot"],
                body.source_job_name,
                new_job_name=body.new_job_name,
                new_vm_uuid=body.new_vm_uuid,
                target_repository_id=body.repository_id,
                trusted_role=request.state.user["role"],
                registry_evidence=collected["registryEvidence"],
                copy_secrets=False,
            )
            result = apply_clone_candidate(
                internal_review,
                actor=request.state.user["username"],
                intent_id=str(body.idempotency_key),
                expected_digest=body.review_digest,
                store=gateway.store,
                executor=gateway.lifecycle_clone_executor,
            )
            return _clone_contract(result, collected)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(409, "Clone apply is unavailable. No authoritative write was started.")

    @router.post("/api/jobs/lifecycle/remove/review")
    async def remove_review(body: RetirementReviewRequest, request: Request):
        _require_admin(request)
        _require_confirmed_post(request)
        return _remove_review(get_gateway(), body.job_name, request.state.user["role"])

    @router.post("/api/jobs/lifecycle/remove", status_code=202)
    async def remove_apply(body: RetirementApplyRequest, request: Request):
        _require_admin(request)
        _require_confirmed_post(request)
        if body.confirmed is not True:
            raise HTTPException(409, "Retirement confirmation is required.")
        gateway = get_gateway()
        if _prereq_blockers(gateway):
            raise HTTPException(409, "Lifecycle removal prerequisites are not ready.")
        if not _actor_allowed(gateway, request.state.user["username"]):
            raise HTTPException(403, "Administrator permission was revoked.")
        review = _remove_review(gateway, body.job_name, request.state.user["role"])
        if review["proofRevision"] != body.proof_revision or review["reviewDigest"] != body.review_digest:
            raise HTTPException(409, "Removal review changed. Review again before apply.")
        if review["readiness"] != "candidate_ready" or not review["executionSupported"]:
            raise HTTPException(409, review["summary"])
        try:
            proof = gateway.lifecycle_retirement_collector.collect_retirement_proof(body.job_name, request.state.user["role"])
            from backend.lifecycle_retirement import execute_retirement

            return execute_retirement(
                gateway.store,
                gateway.lifecycle_retirement_executor,
                proof,
                actor=request.state.user["username"],
                idempotency_key=str(body.idempotency_key),
                review_digest=body.review_digest,
                proof_revision=body.proof_revision,
            )
        except HTTPException:
            raise
        except ValueError:
            raise HTTPException(409, "Retirement review changed or prerequisites are no longer satisfied.")
        except Exception:
            raise HTTPException(409, "Retirement apply is unavailable. No authoritative write was started.")

    @router.get("/api/jobs/lifecycle/retired")
    async def retired(request: Request, jobName: str = Query(pattern=r"^[A-Za-z0-9_.-]{1,128}$")):
        _require_admin(request)
        gateway = get_gateway()
        try:
            from backend.lifecycle_retirement import retired_job_discovery

            result = retired_job_discovery(gateway.store, jobName)
        except Exception:
            raise HTTPException(409, "Retired-job discovery is unavailable.")
        if not result:
            raise HTTPException(404, "Retired-job discovery not found.")
        return result

    return router
