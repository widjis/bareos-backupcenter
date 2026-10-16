"""Authoritative lifecycle review/apply orchestration for server-owned evidence."""
from __future__ import annotations

import hashlib
import json

from backend.job_lifecycle import preview_disable_schedule
from backend.lifecycle_target import candidate_capabilities, invoke as lifecycle_invoke


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _block(code, summary):
    return {"code": code, "summary": summary}


def _impact(code, severity, summary):
    return {"code": code, "severity": severity, "summary": summary}


def _assignment_snapshot(assignment, job_name, proof_revision):
    return {
        "stable_id": str(assignment.get("stable_id") or assignment["inventory_vm_id"]),
        "job_name": job_name,
        "selection_revision": proof_revision,
        "snapshot_revision": proof_revision,
        "identity_revision": proof_revision,
        "managed_vm_ids": [str(assignment["instance_uuid"])],
        "repository_id": assignment["storage_name"],
    }


def _ops(store, job_name):
    rows = []
    for row in store.lifecycle_operations(job_name):
        rows.append(
            {
                "operation_id": str(row["id"]),
                "kind": "lifecycle_apply" if row["kind"] == "provision" else "backup",
                "state": row["state"].lower(),
                "summary": (row.get("parameters") or {}).get("summary") or f"{row['kind']} is {row['state']}.",
            }
        )
    return rows


def _current(job_name):
    return lifecycle_invoke({"action": "current", "job_name": job_name})


def _review(action, job_name, definition=None):
    return lifecycle_invoke({"action": "review", "lifecycle_action": action, "job_name": job_name, "definition": definition})


def review_disable(store, values, job_name, trusted_role):
    caps = candidate_capabilities(values)
    impacts = []
    blockers = []
    try:
        assignment = store.assignment_detail(job_name)
    except ValueError as exc:
        assignment = None
        blockers.append(_block("assignment_conflict", str(exc)))
    if not assignment:
        blockers.append(_block("missing_stable_identity_proof", "Managed persisted assignment for this job is unavailable."))
    else:
        if not assignment.get("instance_uuid") or not assignment.get("storage_name"):
            blockers.append(_block("missing_stable_identity_proof", "Managed assignment is missing VM identity or repository binding."))
    try:
        current = _current(job_name)
    except Exception as exc:
        current = None
        blockers.append(_block("missing_registry_proof", str(exc)))
    if current and current.get("blockers"):
        blockers.extend(current["blockers"])
    if blockers:
        return {
            "jobName": job_name,
            "action": "disable_schedule",
            "readiness": "blocked",
            "reviewDigest": _digest({"action": "disable_schedule", "jobName": job_name, "blockers": blockers}),
            "proofRevision": 0,
            "blockers": blockers[:8],
            "impacts": impacts,
            "summary": "Disable review is blocked until authoritative assignment and current managed job proof are available.",
            "executionSupported": False,
            **caps,
        }
    proof_revision = current["proofRevision"]
    preview = preview_disable_schedule(
        {
            "actor_role": trusted_role,
            "proof_coverage": current.get("proofCoverage", []),
            "proof_revision": proof_revision,
            "snapshot": _assignment_snapshot(assignment, job_name, proof_revision),
            "resources": current["resources"],
            "operations": current.get("operations", []) + _ops(store, job_name),
            "dependencies": current["dependencies"],
            "unresolved_intents": current.get("unresolvedIntents", []),
        },
        trusted_role=trusted_role,
    ).model_dump(mode="json")
    impacts.extend(preview["impacts"])
    if not caps["installedReady"]:
        impacts.append(_impact("candidate_not_installed", "info", "Lifecycle candidate logic is implemented, but installed helper readiness is still blocked here."))
    helper_review = None
    if not preview["blockers"]:
        try:
            helper_review = _review("disable", job_name)
        except Exception as exc:
            preview["blockers"].append(_block("helper_review_failed", str(exc)))
    readiness = "candidate_ready" if not preview["blockers"] and helper_review else "blocked"
    return {
        "jobName": job_name,
        "action": "disable_schedule",
        "readiness": readiness,
        "reviewDigest": (helper_review or {}).get("reviewDigest") or preview["review_digest"],
        "digest": (helper_review or {}).get("reviewDigest") or preview["review_digest"],
        "proofRevision": proof_revision,
        "blockers": preview["blockers"],
        "impacts": impacts[:8],
        "summary": "Disable suppresses automatic schedule, after-job and retry delivery while preserving backups and restoreability.",
        "executionSupported": bool(caps["applyEnabled"] and not preview["blockers"]),
        "definition": (helper_review or {}).get("definition") or current["definition"],
        "currentDigest": current.get("currentDigest"),
        **caps,
    }


def review_enable(store, values, job_name, trusted_role):
    caps = candidate_capabilities(values)
    try:
        current = _current(job_name)
    except Exception:
        payload = {"jobName": job_name, "action": "enable_schedule", "readiness": "blocked", "proofRevision": 0, "blockers": [_block("missing_native_proof", "The installed lifecycle helper and its current job state are unavailable.")], "impacts": [], "summary": "Enable requires the installed lifecycle helper and a verified prior disable receipt.", "executionSupported": False, **caps}
        payload["reviewDigest"] = _digest(payload)
        return payload
    revision = store.latest_lifecycle_revision(job_name)
    blockers = []
    if not revision or revision["state"] != "Validated" or revision["payload"].get("action") != "disable":
        blockers.append(_block("missing_disable_receipt", "Enable requires the last validated disable receipt and reviewed managed definition."))
    if _ops(store, job_name):
        blockers.append(_block("pending_operation", "Another lifecycle operation is still unresolved for this job."))
    saved = (revision or {}).get("payload", {}).get("definition")
    if current.get("blockers"):
        blockers.extend(current["blockers"])
    helper_review = None
    if not blockers:
        try:
            helper_review = _review("enable", job_name, saved)
        except Exception as exc:
            blockers.append(_block("helper_review_failed", str(exc)))
    review_digest = (helper_review or {}).get("reviewDigest") or _digest({"action": "enable", "jobName": job_name, "proofRevision": current["proofRevision"], "definition": saved})
    return {
        "jobName": job_name,
        "action": "enable_schedule",
        "readiness": "candidate_ready" if not blockers and helper_review else "blocked",
        "reviewDigest": review_digest,
        "digest": review_digest,
        "proofRevision": current["proofRevision"],
        "blockers": blockers[:8],
        "impacts": [_impact("managed_definition_restore", "warning", "Enable restores the last reviewed managed schedule/hook definition only.")],
        "summary": "Enable restores the reviewed schedule and dependency hooks when the current proof still matches.",
        "executionSupported": bool(caps["applyEnabled"] and not blockers and helper_review),
        "definition": (helper_review or {}).get("definition") or saved,
        "currentDigest": current.get("currentDigest"),
        **caps,
    }


def prepare_apply(store, actor, review, action, request_id):
    if review["readiness"] != "candidate_ready":
        raise ValueError("Lifecycle action is not ready for apply.")
    return store.prepare_lifecycle(
        request_id,
        actor,
        {
            "kind": "lifecycle",
            "action": action,
            "jobName": review["jobName"],
            "proofRevision": review["proofRevision"],
            "reviewDigest": review["reviewDigest"],
            "definition": review.get("definition"),
            "summary": review["summary"],
        },
    )
