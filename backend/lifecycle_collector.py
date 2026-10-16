"""Conservative read-only disable preview collector for real monitoring snapshots."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.lifecycle_adapter import build_disable_preview


def _digest(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


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


def _final(job_name: str, blockers: list[dict[str, str]], impacts: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "jobName": job_name,
        "action": "disable_schedule",
        "executionSupported": False,
        "blockers": _unique(blockers)[:8],
        "impacts": _unique(impacts)[:8],
    }
    return {**payload, "digest": _digest(payload)}


def collect_disable_preview(snapshot: dict, job_name: str, *, trusted_role: str) -> dict:
    impacts = [
        _impact("read_only_preview", "info", "Disable preview remains read-only; execution is not supported here."),
        _impact(
            "future_collectors_required",
            "info",
            "Authoritative follow-up collectors are still required for stable managed identity/repository bindings, current schedule ownership, and durable operations/dependencies/intents.",
        ),
    ]
    blockers: list[dict[str, str]] = []
    if trusted_role and trusted_role != "Admin":
        blockers.append(_block("permission_denied", "Administrator permission is required for disable review."))
    if not trusted_role:
        blockers.append(_block("missing_trusted_role", "Trusted server role is required; snapshot role labels are not authoritative."))
    if not isinstance(snapshot, dict):
        blockers.append(_block("invalid_snapshot", "Current monitoring snapshot is unavailable for disable review."))
        return _final(job_name, blockers, impacts)
    jobs = snapshot.get("jobs")
    if not isinstance(jobs, list):
        blockers.append(_block("partial_snapshot", "Current monitoring snapshot does not include the bounded jobs list."))
        return _final(job_name, blockers, impacts)
    if not any(isinstance(row, dict) and row.get("name") == job_name for row in jobs):
        blockers.append(_block("job_not_found", f"Current snapshot does not include managed job {job_name} by exact name."))
        return _final(job_name, blockers, impacts)
    if snapshot.get("connection") == "stale":
        blockers.append(_block("stale_snapshot", "Current monitoring snapshot is stale; collect a fresh connected snapshot before review."))
    elif snapshot.get("connection") == "partial" or any(
        key in (snapshot.get("sourceErrors") or {}) for key in ("jobs", "filesets")
    ):
        blockers.append(_block("partial_snapshot", "Current monitoring snapshot is partial; disable review needs complete job and configuration evidence."))
    if snapshot.get("connection") not in ("connected", "partial", "stale"):
        blockers.append(_block("source_unavailable", "Connected server evidence is not available for review."))
    persistence = snapshot.get("persistence")
    if not isinstance(persistence, dict) or persistence.get("state") != "connected":
        blockers.append(_block("missing_persistence_proof", "Application persistence is not connected; authoritative workload and operation evidence is unavailable."))
    adapter = build_disable_preview({"job_name": job_name}, job_name, trusted_role=trusted_role or "")
    blockers.extend(adapter["blockers"])
    blockers.extend(
        [
            _block(
                "missing_stable_identity_proof",
                "Collect exact managed stable identity, persisted VM assignment, repository binding and current identity revision from authoritative server-owned state.",
            ),
            _block(
                "missing_resource_proof",
                "Collect reviewed schedule/resource ownership and usage from current configuration revisions or live apply receipts.",
            ),
            _block(
                "missing_registry_proof",
                "Collect durable operations, dependency and unresolved-intent evidence from the application journal rather than bounded session windows.",
            ),
        ]
    )
    return _final(job_name, blockers, impacts)
