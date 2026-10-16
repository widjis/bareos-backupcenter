"""Managed live-job registry reconciliation and PostgreSQL persistence.

This module stores authoritative managed live-job ownership separately from
legacy onboarding `protection_assignments`, whose `Retired` rows must never be
revived as proof of current ownership.
"""
from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg2.extras import Json, RealDictCursor


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _block(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _unique(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, str]] = []
    for item in items:
        key = (item["code"], item["summary"])
        if key not in seen:
            seen.add(key)
            rows.append(item)
    return rows[:8]


def _require_dict(value: Any, blockers: list[dict[str, str]], code: str, summary: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        blockers.append(_block(code, summary))
        return {}
    return value


def _stable_id(inventory_connection_id: str, instance_uuid: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"managed-registry:{inventory_connection_id}:{instance_uuid.lower()}"))


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _freshness_blockers(observed: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)
    timestamps = {
        "observedAt": observed.get("observedAt"),
        "config.collectedAt": (observed.get("config") or {}).get("collectedAt"),
        "inventory.syncedAt": (observed.get("inventory") or {}).get("syncedAt"),
    }
    parsed: dict[str, datetime] = {}
    for label, value in timestamps.items():
        if value is None:
            continue
        dt = _parse_timestamp(value)
        if dt is None:
            blockers.append(_block("invalid_source_freshness", f"{label} is not a valid numeric or ISO-8601 timestamp."))
            continue
        parsed[label] = dt
        if dt > now + timedelta(minutes=5):
            blockers.append(_block("future_source", f"{label} is ahead of the current clock and cannot be trusted."))
        if dt < now - timedelta(days=1):
            blockers.append(_block("stale_source", f"{label} is older than the allowed freshness window."))
    if not parsed:
        blockers.append(_block("invalid_source_freshness", "No valid source freshness timestamp was provided."))
    return blockers


def _row_source_digest(row: dict[str, Any]) -> str:
    stable = {
        "jobName": row["jobName"],
        "instanceUuid": row["instanceUuid"],
        "inventoryVmId": row["inventoryVmId"],
        "inventoryConnectionId": row["inventoryConnectionId"],
        "vcenterUuid": row["vcenterUuid"],
        "repositoryId": row["repositoryId"],
        "storageName": row["storageName"],
        "filesetName": row["filesetName"],
        "poolName": row["poolName"],
        "scheduleName": row.get("scheduleName"),
        "jobDefsName": row.get("jobDefsName"),
        "lifecycleState": row["lifecycleState"],
        "configDigest": row["configDigest"],
        "selectorProvenance": row.get("selectorProvenance"),
        "resourceUse": row["resourceUse"],
        "resourceIssues": row.get("resourceIssues", []),
        "sourceCoverage": row["sourceCoverage"],
    }
    return _sha(stable)


def _global_blockers(observed: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    director = _require_dict(observed.get("director"), blockers, "stale_source", "Current Director source proof is unavailable.")
    inventory = _require_dict(observed.get("inventory"), blockers, "stale_source", "Current inventory source proof is unavailable.")
    config = _require_dict(observed.get("config"), blockers, "stale_source", "Current configuration source proof is unavailable.")
    coverage = _require_dict(observed.get("coverage"), blockers, "partial_source", "Source coverage flags are unavailable.")
    collector_blockers = observed.get("collectorBlockers")
    if blockers:
        return blockers
    if director.get("state") != "connected":
        blockers.append(_block("stale_source", "Current Director source is not connected."))
    if inventory.get("state") != "connected":
        blockers.append(_block("stale_source", "Current inventory source is not connected."))
    if config.get("state") != "connected":
        blockers.append(_block("stale_source", "Current configuration source is not connected."))
    for name in ("director", "inventory", "config"):
        row = coverage.get(name)
        if not isinstance(row, dict) or not row.get("complete"):
            blockers.append(_block("partial_source", f"{name.capitalize()} coverage is incomplete or truncated."))
    if director.get("directorName") is None or inventory.get("connectionId") is None or inventory.get("vcenterUuid") is None:
        blockers.append(_block("partial_source", "Source identity is incomplete for Director or inventory."))
    blockers.extend(_freshness_blockers(observed))
    if isinstance(collector_blockers, list):
        for item in collector_blockers:
            if isinstance(item, dict) and item.get("code") and item.get("summary"):
                blockers.append(_block(str(item["code"]), str(item["summary"])))
    return blockers


def reconcile_managed_registry(observed: dict[str, Any], retired_assignments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    retired_assignments = retired_assignments or []
    if not isinstance(observed, dict):
        return {"status": "blocked", "observedAt": _iso(), "blockers": [_block("invalid_observed_payload", "Observed managed registry payload must be a dictionary.")], "entries": [], "sourceDigest": _sha(None)}
    blockers = _global_blockers(observed)
    jobs = observed.get("jobs")
    if not isinstance(jobs, list):
        blockers.append(_block("partial_source", "Observed managed jobs are unavailable."))
        return {"status": "blocked", "observedAt": observed.get("observedAt") or _iso(), "blockers": _unique(blockers), "entries": [], "sourceDigest": _sha(observed)}
    if not jobs:
        blockers.append(_block("partial_source", "Observed managed jobs are unavailable."))
        return {"status": "blocked", "observedAt": observed.get("observedAt") or _iso(), "blockers": _unique(blockers), "entries": [], "sourceDigest": _sha(observed)}
    by_job: dict[str, dict[str, Any]] = {}
    by_uuid: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    retired_by_job = {str(row.get("jobName")): row for row in retired_assignments if row.get("state") == "Retired" and row.get("jobName")}
    retired_by_uuid = {str(row.get("instanceUuid")): row for row in retired_assignments if row.get("state") == "Retired" and row.get("instanceUuid")}
    for row in jobs:
        if not isinstance(row, dict):
            blockers.append(_block("partial_source", "Observed job rows must use the sanitized dictionary contract."))
            continue
        local: list[dict[str, str]] = []
        required = {
            "jobName",
            "instanceUuid",
            "inventoryVmId",
            "inventoryConnectionId",
            "vcenterUuid",
            "repositoryId",
            "storageName",
            "filesetName",
            "poolName",
            "jobConfigPath",
            "jobConfigDigest",
            "filesetConfigPath",
            "filesetConfigDigest",
            "poolConfigPath",
            "poolConfigDigest",
            "storageConfigPath",
            "storageConfigDigest",
            "resourceUse",
            "lifecycleState",
            "configDigest",
            "provenance",
            "sourceCoverage",
            "selectorProvenance",
        }
        miss = sorted(required - set(row))
        if miss:
            local.append(_block("partial_source", f"Observed job {row.get('jobName', 'unknown')} is missing fields: {', '.join(miss)}."))
        if row.get("inventoryIdentity") != "instance-uuid":
            local.append(_block("missing_uuid", f"Job {row.get('jobName', 'unknown')} does not have one verified inventory instance UUID."))
        if row.get("inventoryMatchCount") != 1:
            local.append(_block("duplicate_inventory_match", f"Job {row.get('jobName', 'unknown')} does not resolve to exactly one current inventory VM."))
        source_coverage = row.get("sourceCoverage")
        if not isinstance(source_coverage, dict) or not all(source_coverage.get(name) is True for name in ("director", "inventory", "config")):
            local.append(_block("partial_source", f"Job {row.get('jobName', 'unknown')} is missing complete Director/inventory/config coverage."))
        selector_provenance = row.get("selectorProvenance")
        if not isinstance(selector_provenance, dict) or selector_provenance.get("matchCount") != 1:
            local.append(_block("duplicate_inventory_match", f"Job {row.get('jobName', 'unknown')} does not prove one exact inventory match from its configured selector."))
        resource_use = row.get("resourceUse")
        if not isinstance(resource_use, dict):
            local.append(_block("resource_partial", f"Job {row.get('jobName', 'unknown')} is missing resource accounting."))
        else:
            expected = ["job", "fileset", "pool", "storage", "jobdefs"]
            if row.get("scheduleName"):
                expected.append("schedule")
            for name in expected:
                usage = resource_use.get(name)
                if not isinstance(usage, dict) or usage.get("accounted") is not True or type(usage.get("usageCount")) is not int or usage["usageCount"] < 1:
                    local.append(_block("resource_partial", f"Job {row.get('jobName', 'unknown')} does not have complete {name} usage accounting."))
        issues = row.get("resourceIssues")
        if isinstance(issues, list):
            for item in issues:
                if isinstance(item, dict) and item.get("code") and item.get("summary"):
                    local.append(_block(str(item["code"]), str(item["summary"])))
        if row.get("jobName") in retired_by_job or row.get("instanceUuid") in retired_by_uuid:
            local.append(_block("conflicting_retired_assignment", f"Job {row.get('jobName', 'unknown')} conflicts with a retired staged assignment and must be reviewed manually."))
        if row.get("jobName") in by_job:
            local.append(_block("duplicate_job_name", f"Managed job {row['jobName']} appears more than once in the observed source set."))
        if row.get("instanceUuid") in by_uuid:
            local.append(_block("duplicate_vm_uuid", f"VM UUID {row['instanceUuid']} appears in more than one managed job."))
        if local:
            blockers.extend(local)
            continue
        by_job[row["jobName"]] = row
        by_uuid[row["instanceUuid"]] = row
        stable_id = _stable_id(row["inventoryConnectionId"], row["instanceUuid"])
        proof_snapshot = {
            "jobName": row["jobName"],
            "stableId": stable_id,
            "instanceUuid": row["instanceUuid"],
            "inventoryVmId": row["inventoryVmId"],
            "inventoryConnectionId": row["inventoryConnectionId"],
            "vcenterUuid": row["vcenterUuid"],
            "repositoryId": row["repositoryId"],
            "storageName": row["storageName"],
            "filesetName": row["filesetName"],
            "poolName": row["poolName"],
            "scheduleName": row.get("scheduleName"),
            "jobDefsName": row.get("jobDefsName"),
            "lifecycleState": row["lifecycleState"],
            "dependencies": list(row.get("dependencies", [])),
            "selectorProvenance": row["selectorProvenance"],
            "resourceUse": row["resourceUse"],
            "configPaths": {k: row.get(k) for k in ("jobConfigPath", "filesetConfigPath", "poolConfigPath", "storageConfigPath", "scheduleConfigPath", "jobDefsConfigPath")},
            "configDigests": {k: row.get(k) for k in ("jobConfigDigest", "filesetConfigDigest", "poolConfigDigest", "storageConfigDigest", "scheduleConfigDigest", "jobDefsConfigDigest")},
            "sourceCoverage": row["sourceCoverage"],
            "provenance": row["provenance"],
        }
        entries.append(
            {
                "stableId": stable_id,
                "inventoryVmId": row["inventoryVmId"],
                "inventoryConnectionId": row["inventoryConnectionId"],
                "instanceUuid": row["instanceUuid"],
                "vcenterUuid": row["vcenterUuid"],
                "jobName": row["jobName"],
                "repositoryId": row["repositoryId"],
                "storageName": row["storageName"],
                "filesetName": row["filesetName"],
                "poolName": row["poolName"],
                "scheduleName": row.get("scheduleName"),
                "jobDefsName": row.get("jobDefsName"),
                "lifecycleState": row["lifecycleState"],
                "configurationDigest": row["configDigest"],
                "sourceDigest": _row_source_digest(row),
                "proofSnapshot": proof_snapshot,
                "provenance": row["provenance"],
            }
        )
    return {
        "status": "ready" if not blockers else "blocked",
        "observedAt": observed.get("observedAt") or _iso(),
        "blockers": _unique(blockers),
        "entries": entries if not blockers else [],
        "sourceDigest": _sha(
            {
                "jobs": [
                    {
                        "jobName": row.get("jobName"),
                        "sourceDigest": _row_source_digest(row) if isinstance(row, dict) and {"jobName", "resourceUse", "sourceCoverage", "configDigest"} <= set(row) else None,
                    }
                    for row in jobs
                    if isinstance(row, dict)
                ],
                "director": {"directorName": (observed.get("director") or {}).get("directorName"), "version": (observed.get("director") or {}).get("version")},
                "inventory": {"connectionId": (observed.get("inventory") or {}).get("connectionId"), "vcenterUuid": (observed.get("inventory") or {}).get("vcenterUuid")},
                "config": {"jobCount": (observed.get("config") or {}).get("jobCount"), "managedJobCount": (observed.get("config") or {}).get("managedJobCount")},
            }
        ),
    }


class ManagedRegistryRepository:
    def __init__(self, store):
        self.store = store
        self.connection_id = store.connection_id

    def _connect(self):
        return self.store.connect()

    def read_retired_assignments(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT pa.inventory_vm_id, pa.instance_uuid, pa.configuration_revision_id, pa.job_name, pa.state,
                           cr.state AS revision_state, cr.payload AS revision_payload
                    FROM backupcenter.protection_assignments pa
                    JOIN backupcenter.configuration_revisions cr
                      ON cr.connection_id=pa.connection_id AND cr.id=pa.configuration_revision_id
                    WHERE pa.connection_id=%s AND pa.state='Retired'
                    ORDER BY pa.updated_at DESC
                    """,
                    (self.connection_id,),
                )
                rows = []
                for row in cur.fetchall():
                    payload = row.get("revision_payload") if isinstance(row.get("revision_payload"), dict) else {}
                    if row.get("revision_state") == "Validated" and payload.get("liveApplied") is True:
                        continue
                    rows.append(
                        {
                            "inventoryVmId": str(row["inventory_vm_id"]),
                            "instanceUuid": row["instance_uuid"],
                            "configurationRevisionId": str(row["configuration_revision_id"]),
                            "jobName": row["job_name"],
                            "state": row["state"],
                        }
                    )
                return rows

    def assignment_detail(self, job_name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT inventory_vm_id, configuration_revision_id, instance_uuid, job_name, stable_id,
                           fileset_name, pool_name, storage_name, lifecycle_state, revision
                    FROM backupcenter.managed_registry_entries
                    WHERE connection_id=%s AND job_name=%s
                    """,
                    (self.connection_id, job_name),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "stable_id": str(row["stable_id"]),
                    "inventory_vm_id": str(row["inventory_vm_id"]),
                    "configuration_revision_id": str(row["configuration_revision_id"]),
                    "instance_uuid": row["instance_uuid"],
                    "policy_id": None,
                    "policy_revision": row["revision"],
                    "job_name": row["job_name"],
                    "fileset_name": row["fileset_name"],
                    "pool_name": row["pool_name"],
                    "storage_name": row["storage_name"],
                    "state": "Registered" if row["lifecycle_state"] in ("enabled", "disabled", "manual_only") else "Blocked",
                }

    def enumerate_entries(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT stable_id, configuration_revision_id, inventory_vm_id, inventory_connection_id,
                           instance_uuid, vcenter_uuid, job_name, repository_id, storage_name, fileset_name,
                           pool_name, schedule_name, jobdefs_name, lifecycle_state, revision,
                           configuration_digest, source_digest, proof_snapshot, provenance
                    FROM backupcenter.managed_registry_entries
                    WHERE connection_id=%s
                    ORDER BY job_name
                    """,
                    (self.connection_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def proof_snapshot(self, job_name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT proof_snapshot FROM backupcenter.managed_registry_entries WHERE connection_id=%s AND job_name=%s",
                    (self.connection_id, job_name),
                )
                row = cur.fetchone()
                return dict(row["proof_snapshot"]) if row else None

    def _receipt(self, cur, status: str, payload: dict[str, Any]) -> dict[str, Any]:
        receipt_id = str(uuid4())
        cur.execute(
            """
            INSERT INTO backupcenter.managed_registry_receipts(id, connection_id, observed_digest, status, payload)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (receipt_id, self.connection_id, payload["sourceDigest"], status, Json(payload)),
        )
        return {"id": receipt_id, "status": status, "payload": payload}

    def _assert_persisted_inventory(self, cur, entry: dict[str, Any]) -> None:
        cur.execute(
            """
            SELECT iv.id, iv.connection_id, iv.instance_uuid, iv.visible, iv.payload,
                   snap.payload->>'vcenterUuid' AS snapshot_vcenter_uuid
            FROM backupcenter.inventory_vms iv
            JOIN backupcenter.inventory_snapshots snap ON snap.connection_id=iv.connection_id
            WHERE iv.id=%s AND iv.connection_id=%s
            """,
            (entry["inventoryVmId"], entry["inventoryConnectionId"]),
        )
        row = cur.fetchone()
        if not row or row.get("visible") is not True or row.get("instance_uuid") != entry["instanceUuid"]:
            raise ValueError("Managed registry inventory proof is not present in authoritative persisted inventory.")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if payload.get("identityQuality") != "instance-uuid":
            raise ValueError("Managed registry inventory proof does not retain instance-uuid quality in persistence.")
        selector = ((entry.get("proofSnapshot") or {}).get("selectorProvenance") or {}).get("matchedInventory") or {}
        if selector:
            checks = (("name", "name"), ("folder", "folder"), ("datacenter", "datacenter"))
            for persisted_key, selector_key in checks:
                wanted = selector.get(selector_key)
                if wanted is not None and payload.get(persisted_key) != wanted:
                    raise ValueError("Managed registry selector proof does not match authoritative persisted inventory.")
        if row.get("snapshot_vcenter_uuid") != entry["vcenterUuid"]:
            raise ValueError("Managed registry vCenter identity does not match the authoritative persisted inventory snapshot.")

    def reconcile(self, observed: dict[str, Any], expected_revisions: dict[str, int] | None = None) -> dict[str, Any]:
        candidate = reconcile_managed_registry(observed, self.read_retired_assignments())
        expected_revisions = expected_revisions or {}
        with closing(self._connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "INSERT INTO backupcenter.connections(id,name,provider) VALUES(%s,'Bareos Director','bareos') ON CONFLICT(id) DO NOTHING",
                    (self.connection_id,),
                )
                if candidate["status"] != "ready":
                    return self._receipt(cur, "Blocked", candidate)
                applied: list[dict[str, Any]] = []
                changed = False
                for entry in candidate["entries"]:
                    self._assert_persisted_inventory(cur, entry)
                    cur.execute(
                        """
                        SELECT stable_id, configuration_revision_id, revision, job_name, instance_uuid,
                               source_digest, configuration_digest
                        FROM backupcenter.managed_registry_entries
                        WHERE connection_id=%s AND stable_id=%s
                        FOR UPDATE
                        """,
                        (self.connection_id, entry["stableId"]),
                    )
                    existing = cur.fetchone()
                    cur.execute(
                        """
                        SELECT stable_id FROM backupcenter.managed_registry_entries
                        WHERE connection_id=%s AND (job_name=%s OR instance_uuid=%s) AND stable_id<>%s
                        FOR UPDATE
                        """,
                        (self.connection_id, entry["jobName"], entry["instanceUuid"], entry["stableId"]),
                    )
                    if cur.fetchone():
                        raise ValueError("Registry uniqueness conflict detected for job name or VM UUID.")
                    if existing and existing["job_name"] != entry["jobName"]:
                        raise ValueError("Managed registry detected a job rename conflict and cannot guess ownership.")
                    expected = expected_revisions.get(entry["stableId"])
                    if expected is not None and existing and existing["revision"] != expected:
                        raise ValueError("Managed registry revision changed before reconcile could be applied.")
                    if existing and existing["source_digest"] == entry["sourceDigest"] and existing["configuration_digest"] == entry["configurationDigest"]:
                        applied.append({"stableId": entry["stableId"], "jobName": entry["jobName"], "revision": existing["revision"], "replay": True})
                        continue
                    changed = True
                    next_revision = (existing["revision"] + 1) if existing else 1
                    revision_id = str(uuid4())
                    if existing:
                        cur.execute(
                            """
                            UPDATE backupcenter.managed_registry_entries
                            SET configuration_revision_id=%s, inventory_vm_id=%s, inventory_connection_id=%s,
                                vcenter_uuid=%s, job_name=%s, repository_id=%s, storage_name=%s, fileset_name=%s,
                                pool_name=%s, schedule_name=%s, jobdefs_name=%s, lifecycle_state=%s,
                                revision=%s, configuration_digest=%s, source_digest=%s, proof_snapshot=%s,
                                provenance=%s, updated_at=now()
                            WHERE connection_id=%s AND stable_id=%s
                            """,
                            (
                                revision_id,
                                entry["inventoryVmId"],
                                entry["inventoryConnectionId"],
                                entry["vcenterUuid"],
                                entry["jobName"],
                                entry["repositoryId"],
                                entry["storageName"],
                                entry["filesetName"],
                                entry["poolName"],
                                entry["scheduleName"],
                                entry["jobDefsName"],
                                entry["lifecycleState"],
                                next_revision,
                                entry["configurationDigest"],
                                entry["sourceDigest"],
                                Json(entry["proofSnapshot"]),
                                Json(entry["provenance"]),
                                self.connection_id,
                                entry["stableId"],
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO backupcenter.managed_registry_entries(
                                id, connection_id, configuration_revision_id, stable_id, inventory_vm_id,
                                inventory_connection_id, instance_uuid, vcenter_uuid, job_name, repository_id,
                                storage_name, fileset_name, pool_name, schedule_name, jobdefs_name,
                                lifecycle_state, revision, configuration_digest, source_digest,
                                proof_snapshot, provenance
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                str(uuid4()),
                                self.connection_id,
                                revision_id,
                                entry["stableId"],
                                entry["inventoryVmId"],
                                entry["inventoryConnectionId"],
                                entry["instanceUuid"],
                                entry["vcenterUuid"],
                                entry["jobName"],
                                entry["repositoryId"],
                                entry["storageName"],
                                entry["filesetName"],
                                entry["poolName"],
                                entry["scheduleName"],
                                entry["jobDefsName"],
                                entry["lifecycleState"],
                                next_revision,
                                entry["configurationDigest"],
                                entry["sourceDigest"],
                                Json(entry["proofSnapshot"]),
                                Json(entry["provenance"]),
                            ),
                        )
                    applied.append({"stableId": entry["stableId"], "jobName": entry["jobName"], "revision": next_revision, "replay": False})
                receipt = {
                    "status": "applied" if changed else "replay",
                    "observedAt": candidate["observedAt"],
                    "blockers": [],
                    "applied": applied,
                    "sourceDigest": candidate["sourceDigest"],
                }
                return self._receipt(cur, "Applied" if changed else "Replay", receipt)
