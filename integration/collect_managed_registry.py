"""Collect sanitized managed-registry source evidence without writing to PostgreSQL."""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local" / "lifecycle-production-b6" / "registry-observed.json"
WRAPPER = Path(r"C:\Scripts\Projects\bareos\Invoke-BareosRemote.ps1")
REMOTE_PYTHON = "/opt/bareos-api-venv/bin/python"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha(value: Any) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _sanitize(text: str) -> str:
    return re.sub(r'(?i)((?:password|vcpass|token|secret|authorization)\s*[=:]\s*)[^\s,;]+', r"\1[redacted]", text)


def _install_dotenv_fallback() -> None:
    try:
        import dotenv  # type: ignore
        return
    except ModuleNotFoundError:
        pass

    def dotenv_values(path: str | Path) -> dict[str, str]:
        values: dict[str, str] = {}
        file = Path(path)
        if not file.exists():
            return values
        for raw in file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    module = types.ModuleType("dotenv")
    module.dotenv_values = dotenv_values
    sys.modules["dotenv"] = module


_install_dotenv_fallback()


REMOTE_SCRIPT = r"""
import hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/opt/bareos-api")
sys.path.insert(0, "/opt/bareos/25.1.1/lib/bareos/vmware-python")

from direct_vm_restore import console

BASE = Path("/etc/bareos/bareos-dir.d")
DIRS = {name: BASE / name for name in ("job", "fileset", "pool", "storage", "schedule", "jobdefs")}

def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha_obj(value):
    return hashlib.sha256(canon(value).encode("utf-8")).hexdigest()

def listify(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def scalar(value):
    values = listify(value)
    return str(values[0]).strip() if values else None

def selector_from_plugin(plugin):
    text = str(plugin)
    if "bareos-fd-vmware" not in text:
        return None
    def pick(name):
        match = re.search(r"(?:^|:)" + re.escape(name) + r"=([^:]+)", text)
        return match.group(1).strip() if match else None
    return {
        "uuid": pick("uuid"),
        "vmname": pick("vmname"),
        "folder": pick("folder"),
        "dc": pick("dc"),
    }

def include_plugins(include):
    values = []
    for item in listify(include):
        if isinstance(item, dict):
            plugin = item.get("plugin")
            values.extend(str(value).strip() for value in listify(plugin) if str(value).strip())
        elif isinstance(item, str):
            values.append(item.strip())
    return values

def read_map(path, parser):
    rows = {}
    duplicates = []
    if not path.exists():
        return rows, duplicates
    for file in sorted(path.glob("*.conf")):
        text = file.read_text(encoding="utf-8", errors="replace")
        parsed = parser(file, text)
        name = parsed.get("name") or file.stem
        if name in rows:
            duplicates.append(name)
        rows[name] = parsed
    return rows, duplicates

def parse_job(file, text):
    def pick(name):
        match = re.search(r"^\s*" + re.escape(name) + r"\s*=\s*\"?([^\n\"]+)\"?\s*$", text, re.M)
        return match.group(1).strip() if match else None
    return {
        "name": pick("Name") or file.stem,
        "path": str(file),
        "digest": sha_text(text),
        "fileset": pick("FileSet"),
        "pool": pick("Pool"),
        "storage": pick("Storage"),
        "schedule": pick("Schedule"),
        "jobdefs": pick("JobDefs"),
        "enabled": pick("Enabled"),
        "dependencyTargets": re.findall(r"^\s*#\s*BackupCenter dependency trigger begin:\s*(\S+)\s*$", text, re.M),
    }

def parse_fileset(file, text):
    name_match = re.search(r"^\s*Name\s*=\s*\"?([^\n\"]+)\"?\s*$", text, re.M)
    plugins = re.findall(r"^\s*Plugin\s*=\s*\"([^\n\"]+)\"\s*$", text, re.M)
    selectors = [row for row in (selector_from_plugin(plugin) for plugin in plugins) if row]
    include_paths = [line.strip()[1:].strip() for line in text.splitlines() if line.strip().startswith("@")]
    return {
        "name": (name_match.group(1).strip() if name_match else file.stem),
        "path": str(file),
        "digest": sha_text(text),
        "selectors": selectors,
        "pluginCount": len(selectors),
        "includePaths": include_paths,
        "includeAccounted": not bool(include_paths),
    }

def parse_named(file, text):
    name_match = re.search(r"^\s*Name\s*=\s*\"?([^\n\"]+)\"?\s*$", text, re.M)
    return {"name": (name_match.group(1).strip() if name_match else file.stem), "path": str(file), "digest": sha_text(text)}

def sanitize_loaded_job(name, value):
    item = {
        "name": name,
        "type": value.get("type"),
        "fileset": value.get("fileset"),
        "pool": value.get("pool"),
        "fullbackuppool": value.get("fullbackuppool"),
        "incrementalbackuppool": value.get("incrementalbackuppool"),
        "differentialbackuppool": value.get("differentialbackuppool"),
        "storage": [str(v).strip() for v in listify(value.get("storage")) if str(v).strip()],
        "schedule": value.get("schedule") or "",
        "jobdefs": value.get("jobdefs") or "",
        "client": value.get("client") or "",
        "afterJobTargets": [],
    }
    item["digest"] = sha_obj(item)
    return item

def sanitize_loaded_fileset(name, value):
    selectors = []
    for plugin in include_plugins(value.get("include")):
        parsed = selector_from_plugin(plugin)
        if parsed:
            selectors.append(parsed)
    item = {"name": name, "selectors": selectors}
    item["digest"] = sha_obj(item)
    return item

def sanitize_loaded_pool(name, value):
    item = {"name": name, "storage": [str(v).strip() for v in listify(value.get("storage")) if str(v).strip()]}
    item["digest"] = sha_obj(item)
    return item

def sanitize_loaded_storage(name, value):
    item = {"name": name, "device": [str(v).strip() for v in listify(value.get("device")) if str(v).strip()]}
    item["digest"] = sha_obj(item)
    return item

def sanitize_loaded_named(name, value):
    item = {"name": name}
    item["digest"] = sha_obj(item)
    return item

disk_jobs, disk_job_dupes = read_map(DIRS["job"], parse_job)
disk_filesets, disk_fileset_dupes = read_map(DIRS["fileset"], parse_fileset)
disk_pools, disk_pool_dupes = read_map(DIRS["pool"], parse_named)
disk_storages, disk_storage_dupes = read_map(DIRS["storage"], parse_named)
disk_schedules, disk_schedule_dupes = read_map(DIRS["schedule"], parse_named)
disk_jobdefs, disk_jobdefs_dupes = read_map(DIRS["jobdefs"], parse_named)

loaded_jobs = {name: sanitize_loaded_job(name, value) for name, value in console("show jobs").get("jobs", {}).items()}
loaded_filesets = {name: sanitize_loaded_fileset(name, value) for name, value in console("show filesets").get("filesets", {}).items()}
loaded_jobdefs = {name: sanitize_loaded_named(name, value) for name, value in console("show jobdefs").get("jobdefs", {}).items()}
loaded_pools = {name: sanitize_loaded_pool(name, value) for name, value in console("show pools").get("pools", {}).items()}
loaded_storages = {name: sanitize_loaded_storage(name, value) for name, value in console("show storages").get("storages", {}).items()}

duplicates = {
    "jobs": sorted(set(disk_job_dupes)),
    "filesets": sorted(set(disk_fileset_dupes)),
    "pools": sorted(set(disk_pool_dupes)),
    "storages": sorted(set(disk_storage_dupes)),
    "schedules": sorted(set(disk_schedule_dupes)),
    "jobdefs": sorted(set(disk_jobdefs_dupes)),
}

payload = {
    "state": "connected",
    "collectedAt": datetime.now(timezone.utc).isoformat(),
    "disk": {
        "jobs": disk_jobs,
        "filesets": disk_filesets,
        "pools": disk_pools,
        "storages": disk_storages,
        "schedules": disk_schedules,
        "jobdefs": disk_jobdefs,
    },
    "loaded": {
        "jobs": loaded_jobs,
        "filesets": loaded_filesets,
        "jobdefs": loaded_jobdefs,
        "pools": loaded_pools,
        "storages": loaded_storages,
    },
}
payload["coverage"] = {
    "complete": not any(duplicates.values()) and all(payload["disk"][name] for name in ("jobs", "filesets", "pools", "storages", "jobdefs")) and all(payload["loaded"][name] for name in ("jobs", "filesets", "jobdefs", "pools", "storages")),
    "jobCount": len(disk_jobs),
    "filesetCount": len(disk_filesets),
    "loadedJobCount": len(loaded_jobs),
    "duplicates": duplicates,
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
"""


def _remote_config() -> dict[str, Any]:
    command = f"env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/opt/bareos/25.1.1/lib/bareos/vmware-python {REMOTE_PYTHON} - <<'PY'\n{REMOTE_SCRIPT}\nPY"
    result = subprocess.run(
        [
            "pwsh",
            "-NoLogo",
            "-NoProfile",
            "-File",
            str(WRAPPER),
            "-Root",
            "-Command",
            command,
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(_sanitize((result.stderr or result.stdout or "Remote collection failed.")[:200]))
    return json.loads(result.stdout.strip())


async def _director_sources() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    from backend.app import SOURCES, gateway, inventory as current_inventory

    g = gateway()
    async with httpx.AsyncClient(verify=g.context, timeout=20, trust_env=False) as client:
        director = await g.get(client, SOURCES["director"])
    inv = await current_inventory().snapshot(True)
    workloads = list((await g.snapshot(True)).get("workloads", []))
    return {"director": director}, inv, workloads


def _retired_assignments() -> list[dict[str, Any]]:
    from backend.persistence import Store
    from backend.managed_registry import ManagedRegistryRepository

    store = Store()
    if not store.configured:
        return []
    try:
        return ManagedRegistryRepository(store).read_retired_assignments()
    except Exception:
        return []


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _storage_name(value: Any) -> str | None:
    values = [str(item).strip() for item in _listify(value) if str(item).strip()]
    return values[0] if values else None


def _lifecycle_state(job: dict[str, Any], disk_job: dict[str, Any]) -> str:
    schedule = job.get("schedule") or "Manual"
    enabled = str(disk_job.get("enabled") or "yes").strip().lower() not in {"no", "false", "0"}
    if schedule == "Manual" and not enabled:
        return "disabled"
    if schedule == "Manual" or not enabled:
        return "manual_only"
    return "enabled"


def _selector_addressing(selectors: list[dict[str, Any]]) -> str:
    if len(selectors) != 1:
        return "ambiguous-selector-set"
    selector = selectors[0]
    if selector.get("uuid"):
        return "uuid"
    if selector.get("vmname") and selector.get("folder") and selector.get("dc"):
        return "name-folder-datacenter"
    return "incomplete-selector"


def _resolve_inventory(selectors: list[dict[str, Any]], inventory_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    addressing = _selector_addressing(selectors)
    selector = selectors[0] if len(selectors) == 1 else {}
    if addressing == "uuid":
        matches = [row for row in inventory_rows if row.get("instanceUuid") == selector.get("uuid")]
    elif addressing == "name-folder-datacenter":
        matches = [
            row
            for row in inventory_rows
            if row.get("name") == selector.get("vmname")
            and row.get("folder") == selector.get("folder")
            and row.get("datacenter") == selector.get("dc")
        ]
    else:
        matches = []
    return matches, {
        "addressing": addressing,
        "selector": {
            "uuid": selector.get("uuid"),
            "vmname": selector.get("vmname"),
            "folder": selector.get("folder"),
            "dc": selector.get("dc"),
        },
        "selectorCount": len(selectors),
        "matchCount": len(matches),
        "matchedInventory": (
            {
                "id": matches[0].get("id"),
                "name": matches[0].get("name"),
                "folder": matches[0].get("folder"),
                "datacenter": matches[0].get("datacenter"),
                "instanceUuid": matches[0].get("instanceUuid"),
                "identityQuality": matches[0].get("identityQuality"),
            }
            if len(matches) == 1
            else None
        ),
    }


def _owners(jobs: dict[str, dict[str, Any]], field: str, value: str | None) -> list[str]:
    if not value:
        return []
    rows = []
    for name, job in jobs.items():
        candidate = _storage_name(job.get(field)) if field == "storage" else job.get(field)
        if candidate == value:
            rows.append(name)
    return sorted(rows)


def _resource_issue(code: str, summary: str) -> dict[str, str]:
    return {"code": code, "summary": summary}


def _job_resource_issues(
    name: str,
    job: dict[str, Any],
    disk_job: dict[str, Any],
    disk: dict[str, Any],
    loaded: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    fileset_name = job.get("fileset")
    pool_name = job.get("pool")
    storage_name = _storage_name(job.get("storage"))
    schedule_name = job.get("schedule") or None
    jobdefs_name = job.get("jobdefs") or None
    if not disk_job:
        issues.append(_resource_issue("missing_disk_resource", f"Job {name} is not present in the authenticated disk configuration."))
        return issues
    if not fileset_name or fileset_name not in loaded.get("filesets", {}) or fileset_name not in disk.get("filesets", {}):
        issues.append(_resource_issue("missing_loaded_resource", f"Job {name} is missing an authenticated FileSet resource."))
    if not pool_name or pool_name not in loaded.get("pools", {}) or pool_name not in disk.get("pools", {}):
        issues.append(_resource_issue("missing_loaded_resource", f"Job {name} is missing an authenticated Pool resource."))
    if not storage_name or storage_name not in loaded.get("storages", {}) or storage_name not in disk.get("storages", {}):
        issues.append(_resource_issue("missing_loaded_resource", f"Job {name} is missing an authenticated Storage resource."))
    if jobdefs_name and jobdefs_name not in loaded.get("jobdefs", {}):
        issues.append(_resource_issue("missing_loaded_resource", f"Job {name} references JobDefs {jobdefs_name} that is not loaded by the Director."))
    if jobdefs_name and jobdefs_name not in disk.get("jobdefs", {}):
        issues.append(_resource_issue("missing_disk_resource", f"Job {name} references JobDefs {jobdefs_name} that is not present on disk."))
    if schedule_name and schedule_name not in disk.get("schedules", {}):
        issues.append(_resource_issue("missing_disk_resource", f"Job {name} references Schedule {schedule_name} that is not present on disk."))
    checks = (
        ("fileset", job.get("fileset"), disk_job.get("fileset")),
        ("pool", job.get("pool"), disk_job.get("pool")),
        ("storage", storage_name, disk_job.get("storage")),
        ("schedule", schedule_name, disk_job.get("schedule") or None),
        ("jobdefs", jobdefs_name, disk_job.get("jobdefs") or None),
    )
    for field, loaded_value, disk_value in checks:
        if disk_value and loaded_value and disk_value != loaded_value:
            issues.append(_resource_issue("loaded_resource_mismatch", f"Job {name} has a mismatched {field} between authenticated disk and loaded resources."))
    fileset = disk.get("filesets", {}).get(fileset_name or "", {})
    include_paths = fileset.get("includePaths", [])
    if include_paths:
        issues.append(_resource_issue("unknown_include_paths", f"Job {name} FileSet uses include paths that are not expanded into authoritative ownership proof."))
    if fileset.get("pluginCount") != 1:
        issues.append(_resource_issue("loaded_resource_mismatch", f"Job {name} FileSet does not contain exactly one VMware selector definition."))
    return issues


def _stable_source_digest(observed_jobs: list[dict[str, Any]], director: dict[str, Any], inventory: dict[str, Any], config: dict[str, Any]) -> str:
    stable_jobs = [
        {
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
            "selectorProvenance": row["selectorProvenance"],
            "resourceUse": row["resourceUse"],
            "resourceIssues": row["resourceIssues"],
        }
        for row in sorted(observed_jobs, key=lambda item: item["jobName"])
    ]
    return _sha(
        {
            "director": {"directorName": director.get("directorName"), "version": director.get("version")},
            "inventory": {"connectionId": inventory.get("connectionId"), "vcenterUuid": inventory.get("vcenterUuid")},
            "config": {
                "diskJobCount": config.get("diskJobCount"),
                "loadedJobCount": config.get("loadedJobCount"),
            },
            "jobs": stable_jobs,
        }
    )


def _build_observed(raw: dict[str, Any], inventory: dict[str, Any], workloads: list[dict[str, Any]], config: dict[str, Any], retired: list[dict[str, Any]]) -> dict[str, Any]:
    director = raw.get("director", {})
    disk = config.get("disk", {}) if isinstance(config.get("disk"), dict) else {}
    loaded = config.get("loaded", {}) if isinstance(config.get("loaded"), dict) else {}
    loaded_jobs = loaded.get("jobs", {}) if isinstance(loaded.get("jobs"), dict) else {}
    loaded_filesets = loaded.get("filesets", {}) if isinstance(loaded.get("filesets"), dict) else {}
    inventory_rows = inventory.get("vms", []) if inventory.get("state") == "connected" else []
    dependency_sources = {name: set((disk.get("jobs", {}).get(name) or {}).get("dependencyTargets", [])) for name in disk.get("jobs", {})}
    observed_jobs: list[dict[str, Any]] = []
    collector_blockers: list[dict[str, str]] = []
    duplicates = ((config.get("coverage") or {}).get("duplicates") or {}) if isinstance(config.get("coverage"), dict) else {}
    for resource_name, names in duplicates.items():
        if names:
            collector_blockers.append(_resource_issue("duplicate_loaded_resource", f"Authenticated disk configuration contains duplicate {resource_name}: {', '.join(sorted(names))}."))
    managed_names = []
    for name, job in loaded_jobs.items():
        fileset = loaded_filesets.get(job.get("fileset") or "")
        selectors = fileset.get("selectors", []) if isinstance(fileset, dict) else []
        if selectors:
            managed_names.append(name)
    for name in sorted(managed_names):
        job = loaded_jobs[name]
        fileset_name = job.get("fileset")
        fileset_loaded = loaded_filesets.get(fileset_name or "", {})
        disk_job = (disk.get("jobs", {}) or {}).get(name, {})
        disk_fileset = (disk.get("filesets", {}) or {}).get(fileset_name or "", {})
        selectors = list(fileset_loaded.get("selectors", []))
        matches, selector_provenance = _resolve_inventory(selectors, inventory_rows)
        matched = matches[0] if len(matches) == 1 and matches[0].get("identityQuality") == "instance-uuid" else None
        local_issues = _job_resource_issues(name, job, disk_job, disk, loaded)
        schedule_name = job.get("schedule") or None
        jobdefs_name = job.get("jobdefs") or None
        storage_name = _storage_name(job.get("storage"))
        owners = {
            "job": {"usageCount": 1, "owners": [name], "accounted": bool(disk_job)},
            "fileset": {"usageCount": len(_owners(loaded_jobs, "fileset", fileset_name)), "owners": _owners(loaded_jobs, "fileset", fileset_name), "accounted": bool(disk_fileset) and not any(item["code"] in {"unknown_include_paths", "missing_loaded_resource"} for item in local_issues)},
            "pool": {"usageCount": len(_owners(loaded_jobs, "pool", job.get("pool"))), "owners": _owners(loaded_jobs, "pool", job.get("pool")), "accounted": job.get("pool") in (disk.get("pools", {}) or {}) and job.get("pool") in (loaded.get("pools", {}) or {})},
            "storage": {"usageCount": len(_owners(loaded_jobs, "storage", storage_name)), "owners": _owners(loaded_jobs, "storage", storage_name), "accounted": storage_name in (disk.get("storages", {}) or {}) and storage_name in (loaded.get("storages", {}) or {})},
            "jobdefs": {"usageCount": len(_owners(loaded_jobs, "jobdefs", jobdefs_name)), "owners": _owners(loaded_jobs, "jobdefs", jobdefs_name), "accounted": (not jobdefs_name) or (jobdefs_name in (disk.get("jobdefs", {}) or {}) and jobdefs_name in (loaded.get("jobdefs", {}) or {}))},
        }
        if schedule_name:
            owners["schedule"] = {"usageCount": len(_owners(loaded_jobs, "schedule", schedule_name)), "owners": _owners(loaded_jobs, "schedule", schedule_name), "accounted": schedule_name in (disk.get("schedules", {}) or {})}
        workload_evidence = next((row.get("evidence") for row in workloads if row.get("job") == name), "Unknown")
        observed_jobs.append(
            {
                "jobName": name,
                "instanceUuid": matched.get("instanceUuid") if matched else None,
                "inventoryVmId": matched.get("id") if matched else None,
                "inventoryConnectionId": inventory.get("connectionId"),
                "inventoryIdentity": matched.get("identityQuality") if matched else None,
                "inventoryMatchCount": len(matches),
                "vcenterUuid": inventory.get("vcenterUuid"),
                "repositoryId": storage_name,
                "storageName": storage_name,
                "filesetName": fileset_name,
                "poolName": job.get("pool"),
                "scheduleName": schedule_name,
                "jobDefsName": jobdefs_name,
                "jobConfigPath": disk_job.get("path"),
                "jobConfigDigest": disk_job.get("digest"),
                "filesetConfigPath": disk_fileset.get("path"),
                "filesetConfigDigest": disk_fileset.get("digest"),
                "poolConfigPath": ((disk.get("pools", {}) or {}).get(job.get("pool")) or {}).get("path"),
                "poolConfigDigest": ((disk.get("pools", {}) or {}).get(job.get("pool")) or {}).get("digest"),
                "storageConfigPath": ((disk.get("storages", {}) or {}).get(storage_name) or {}).get("path"),
                "storageConfigDigest": ((disk.get("storages", {}) or {}).get(storage_name) or {}).get("digest"),
                "scheduleConfigPath": (((disk.get("schedules", {}) or {}).get(schedule_name) or {}).get("path") if schedule_name else None),
                "scheduleConfigDigest": (((disk.get("schedules", {}) or {}).get(schedule_name) or {}).get("digest") if schedule_name else None),
                "jobDefsConfigPath": (((disk.get("jobdefs", {}) or {}).get(jobdefs_name) or {}).get("path") if jobdefs_name else None),
                "jobDefsConfigDigest": (((disk.get("jobdefs", {}) or {}).get(jobdefs_name) or {}).get("digest") if jobdefs_name else None),
                "resourceUse": owners,
                "resourceIssues": local_issues,
                "dependencies": [
                    {"relation": "depends_on", "jobName": source_name}
                    for source_name, targets in sorted(dependency_sources.items())
                    if name in targets
                ]
                + [
                    {"relation": "required_by", "jobName": target}
                    for target in sorted(dependency_sources.get(name, set()))
                ],
                "lifecycleState": _lifecycle_state(job, disk_job),
                "configDigest": _sha(
                    {
                        "loadedJobDigest": job.get("digest"),
                        "loadedFilesetDigest": fileset_loaded.get("digest"),
                        "loadedPoolDigest": ((loaded.get("pools", {}) or {}).get(job.get("pool")) or {}).get("digest"),
                        "loadedStorageDigest": ((loaded.get("storages", {}) or {}).get(storage_name) or {}).get("digest"),
                        "loadedJobDefsDigest": (((loaded.get("jobdefs", {}) or {}).get(jobdefs_name) or {}).get("digest") if jobdefs_name else None),
                        "diskJobDigest": disk_job.get("digest"),
                        "diskFilesetDigest": disk_fileset.get("digest"),
                        "diskPoolDigest": (((disk.get("pools", {}) or {}).get(job.get("pool")) or {}).get("digest")),
                        "diskStorageDigest": (((disk.get("storages", {}) or {}).get(storage_name) or {}).get("digest")),
                        "diskScheduleDigest": (((disk.get("schedules", {}) or {}).get(schedule_name) or {}).get("digest") if schedule_name else None),
                        "diskJobDefsDigest": (((disk.get("jobdefs", {}) or {}).get(jobdefs_name) or {}).get("digest") if jobdefs_name else None),
                    }
                ),
                "provenance": {
                    "directorName": director.get("name"),
                    "directorVersion": director.get("version"),
                    "inventoryServer": inventory.get("server"),
                    "workloadEvidence": workload_evidence,
                    "loadedJobDigest": job.get("digest"),
                    "loadedFilesetDigest": fileset_loaded.get("digest"),
                },
                "selectorProvenance": selector_provenance,
                "sourceCoverage": {
                    "director": director.get("name") is not None and director.get("version") is not None,
                    "inventory": inventory.get("state") == "connected" and inventory.get("connectionId") is not None and inventory.get("vcenterUuid") is not None,
                    "config": bool(disk_job and disk_fileset and job.get("digest") and fileset_loaded.get("digest")),
                },
            }
        )
    observed = {
        "observedAt": config.get("collectedAt"),
        "collectorBlockers": collector_blockers,
        "director": {
            "state": "connected",
            "directorName": director.get("name"),
            "version": director.get("version"),
            "jobCount": len(loaded_jobs),
        },
        "inventory": {
            "state": inventory.get("state"),
            "connectionId": inventory.get("connectionId"),
            "vcenterUuid": inventory.get("vcenterUuid"),
            "server": inventory.get("server"),
            "vmCount": len(inventory_rows),
            "syncedAt": inventory.get("syncedAt"),
        },
        "config": {
            "state": config.get("state"),
            "collectedAt": config.get("collectedAt"),
            "jobCount": len(disk.get("jobs", {}) or {}),
            "diskJobCount": len(disk.get("jobs", {}) or {}),
            "loadedJobCount": len(loaded_jobs),
            "managedJobCount": len(observed_jobs),
        },
        "coverage": {
            "director": {"complete": True},
            "inventory": {"complete": inventory.get("state") == "connected"},
            "config": {"complete": bool((config.get("coverage") or {}).get("complete"))},
        },
        "jobs": observed_jobs,
        "retiredAssignments": retired,
    }
    observed["sourceDigest"] = _stable_source_digest(observed_jobs, observed["director"], observed["inventory"], observed["config"])
    return observed


def _blocked_observed(
    raw: dict[str, Any] | None,
    inventory: dict[str, Any] | None,
    config: dict[str, Any] | None,
    retired: list[dict[str, Any]],
    blockers: list[dict[str, str]],
) -> dict[str, Any]:
    director = raw.get("director", {}) if isinstance(raw, dict) else {}
    disk = (config or {}).get("disk", {}) if isinstance((config or {}).get("disk"), dict) else {}
    loaded = (config or {}).get("loaded", {}) if isinstance((config or {}).get("loaded"), dict) else {}
    return {
        "observedAt": (config or {}).get("collectedAt"),
        "collectorBlockers": blockers,
        "director": {
            "state": director.get("state", "unavailable"),
            "directorName": director.get("name"),
            "version": director.get("version"),
        },
        "inventory": {
            "state": (inventory or {}).get("state", "unavailable"),
            "connectionId": (inventory or {}).get("connectionId"),
            "vcenterUuid": (inventory or {}).get("vcenterUuid"),
            "server": (inventory or {}).get("server"),
            "vmCount": len((inventory or {}).get("vms", []) or []),
            "syncedAt": (inventory or {}).get("syncedAt"),
        },
        "config": {
            "state": (config or {}).get("state", "unavailable"),
            "collectedAt": (config or {}).get("collectedAt"),
            "jobCount": len(disk.get("jobs", {}) or {}),
            "diskJobCount": len(disk.get("jobs", {}) or {}),
            "loadedJobCount": len(loaded.get("jobs", {}) or {}),
            "managedJobCount": 0,
        },
        "coverage": {
            "director": {"complete": bool(raw)},
            "inventory": {"complete": bool(inventory and inventory.get("state") == "connected")},
            "config": {"complete": bool(config and (config.get("coverage") or {}).get("complete"))},
        },
        "jobs": [],
        "retiredAssignments": retired,
        "sourceDigest": _sha(
            {
                "director": director.get("version"),
                "inventory": (inventory or {}).get("connectionId"),
                "config": (config or {}).get("collectedAt"),
                "blockers": blockers,
            }
        ),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    blockers: list[dict[str, str]] = []
    raw = None
    inventory = None
    workloads: list[dict[str, Any]] = []
    config = None
    retired = _retired_assignments()
    try:
        raw, inventory, workloads = await _director_sources()
    except Exception as exc:
        blockers.append({"code": "director_collection_failed", "summary": _sanitize(str(exc)[:200])})
    try:
        config = _remote_config()
    except Exception as exc:
        blockers.append({"code": "config_collection_failed", "summary": _sanitize(str(exc)[:200])})
    observed = _build_observed(raw, inventory, workloads, config, retired) if raw and inventory and config else _blocked_observed(raw, inventory, config, retired, blockers)
    target.write_text(json.dumps(observed, sort_keys=True, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "jobCount": len(observed.get("jobs", [])), "blockers": observed.get("collectorBlockers", [])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
