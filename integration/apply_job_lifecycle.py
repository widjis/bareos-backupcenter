"""Root-owned lifecycle candidate helper with fail-closed dependency loading."""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from uuid import UUID

ROOT = Path("/var/lib/bareos-lifecycle-applications")
LOCK = Path("/var/lib/bareos/vm-chain-retention.lock")
UNRESOLVED_RECEIPT_STATES = {"Dispatching", "Unknown"}
CONTRACT_VERSION = "lifecycle-native-b6"


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _load_lock_module():
    try:
        return importlib.import_module("fcntl")
    except ModuleNotFoundError as exc:
        raise RuntimeError("Lifecycle helper requires POSIX file locking support.") from exc


def _load_policy_module():
    targets = ["integration.apply_backup_policy"]
    if __package__ in (None, ""):
        targets.append("apply_backup_policy")
    last_exc = None
    for name in targets:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            last_exc = exc
            expected = {name, name.split(".")[-1], "integration"}
            if exc.name not in expected:
                raise RuntimeError(f"Lifecycle helper dependency unavailable: {exc.name}.") from exc
    raise RuntimeError("Lifecycle helper dependency unavailable: apply_backup_policy.") from last_exc


def _load_resource_module():
    targets = ["integration.lifecycle_resource_executor"]
    if __package__ in (None, ""):
        targets.append("lifecycle_resource_executor")
    last_exc = None
    for name in targets:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            last_exc = exc
            expected = {name, name.split(".")[-1], "integration"}
            if exc.name not in expected:
                raise RuntimeError(f"Lifecycle helper dependency unavailable: {exc.name}.") from exc
    raise RuntimeError("Lifecycle helper dependency unavailable: lifecycle_resource_executor.") from last_exc


def transport_ready():
    policy = _load_policy_module()
    resource = _load_resource_module()
    _load_lock_module()
    return {
        "helperPath": str(Path(__file__).resolve()),
        "policyHelperPath": str(Path(policy.__file__).resolve()),
        "resourceExecutorPath": str(Path(resource.__file__).resolve()),
    }


def _safe_path_ready(path: Path, *, allow_missing: bool = False):
    if path.is_symlink():
        return False
    if allow_missing and not path.exists():
        return True
    try:
        state = path.stat()
    except FileNotFoundError:
        return False
    return state.st_uid == 0 and not (state.st_mode & 0o022)


def capabilities():
    ready = transport_ready()
    resource = _load_resource_module()
    value = resource.describe_capabilities()
    lock_ready = False
    try:
        with _lock():
            lock_ready = True
    except Exception:
        lock_ready = False
    secure_paths_ready = all(
        (
            _safe_path_ready(Path(ready["helperPath"])),
            _safe_path_ready(Path(ready["policyHelperPath"])),
            _safe_path_ready(ROOT, allow_missing=True),
            _safe_path_ready(LOCK.parent),
        )
    )
    value.update(
        {
            "contractVersion": CONTRACT_VERSION,
            "helperHash": _sha_bytes(Path(__file__).read_bytes()),
            "policyHelperHash": _sha_bytes(Path(ready["policyHelperPath"]).read_bytes()),
            "helperPath": ready["helperPath"],
            "policyHelperPath": ready["policyHelperPath"],
            "resourceExecutorPath": ready["resourceExecutorPath"],
            "transportReady": True,
            "locksReady": bool(value.get("locksReady")) and lock_ready,
            "securePathsReady": bool(value.get("securePathsReady")) and secure_paths_ready,
            "prerequisitesComplete": bool(value.get("prerequisitesComplete")) and lock_ready and secure_paths_ready,
        }
    )
    return value


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text(path: Path) -> str | None:
    return path.read_text() if path.exists() else None


def _fsync_file(path: Path):
    with path.open("r+b") as stream:
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_dir(path: Path):
    handle = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def _write_json_atomic(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        Path(temp).unlink(missing_ok=True)


def _resource_key(text: str, directive: str):
    match = re.search(rf"^\s*{re.escape(directive)}\s*=\s*(\S+)", text, re.M)
    return match.group(1) if match else None


def _job_name(vm: str) -> str:
    return "VMware-" + vm


def _managed_scope(policy, job_name: str) -> str:
    _require(job_name.startswith("VMware-"), "Job is outside managed lifecycle scope.")
    vm = job_name[7:]
    _require(vm in policy.NAMES, "Job is outside managed lifecycle scope.")
    return vm


def _job_map(policy):
    job_dir = policy.BASE / "job"
    return {path.stem: path.read_text() for path in sorted(job_dir.glob("*.conf"))}


def _after_job_runtime_state_dir() -> Path:
    return Path(os.environ.get("BACKUPCENTER_AFTER_JOB_STATE", "/var/lib/bareos-after-job-runtime"))


def _runtime_lock_path(job_name: str) -> Path:
    return _after_job_runtime_state_dir() / "locks" / f"{job_name}.target.lock"


def _target_block_present(text: str, target: str) -> bool:
    return f"# BackupCenter dependency trigger begin: {target}" in text and f"# BackupCenter dependency trigger end: {target}" in text


def _retry_disabled(job_text: str) -> bool:
    values = {name: _resource_key(job_text, name) for name in ("Reschedule On Error", "Reschedule Times", "Reschedule Interval", "Rerun Failed Levels")}
    return values["Reschedule On Error"] == "no" and not values["Reschedule Times"] and not values["Reschedule Interval"] and not values["Rerun Failed Levels"]


def _lifecycle_state(policy, job_name: str):
    vm = _managed_scope(policy, job_name)
    job_path, pool_path, schedule_path = policy.paths(vm)
    job_text = job_path.read_text()
    pool_text = pool_path.read_text()
    schedule_name = _resource_key(job_text, "Schedule")
    schedule_text = _read_text(schedule_path if schedule_name == schedule_path.stem else policy.BASE / "schedule" / f"{schedule_name}.conf") or ""
    definition = policy.policy_marker(job_text)
    _require(definition is not None, "Managed lifecycle marker is missing from the job configuration.")
    all_jobs = _job_map(policy)
    jobs = {name: text for name, text in all_jobs.items() if name in policy.NAMES}
    enabled_ok = False
    enabled_error = "Managed lifecycle state is inconsistent."
    try:
        policy.verify_retry_directives(job_text, definition)
        policy.verify_hooks(jobs, job_name, definition)
        if definition["trigger_mode"] == "calendar":
            _require(schedule_name is not None, "Current managed calendar schedule binding is missing.")
        else:
            _require(schedule_name in (None, "Manual"), "After-job scheduling must not keep a managed clock schedule.")
        enabled_ok = True
    except Exception as exc:
        enabled_error = str(exc)
    disabled_ok = schedule_name is None and _retry_disabled(job_text)
    if disabled_ok and definition["trigger_mode"] == "after_job":
        source = (definition.get("after_job") or {}).get("source_job")
        _require(source and source.startswith("VMware-"), "Managed after-job source is missing from the marker.")
        disabled_ok = not _target_block_present(policy.paths(source[7:])[0].read_text(), job_name)
    _require(enabled_ok or disabled_ok, enabled_error)
    return {
        "vm": vm,
        "job_path": job_path,
        "pool_path": pool_path,
        "schedule_path": schedule_path,
        "job_text": job_text,
        "pool_text": pool_text,
        "schedule_text": schedule_text,
        "schedule_name": schedule_name,
        "definition": definition,
        "lifecycle_state": "disabled" if disabled_ok and not enabled_ok else "enabled",
        "jobs": jobs,
        "all_jobs": all_jobs,
    }


def _resource_rows(policy, state, proof_revision: int):
    job_refs = list(state["all_jobs"].values())
    job_name = _job_name(state["vm"])
    fileset = _resource_key(state["job_text"], "FileSet")
    pool = _resource_key(state["job_text"], "Pool")
    schedule_name = state["schedule_name"] or state["schedule_path"].stem
    rows = [
        {"resource_type": "job", "resource_name": job_name, "ownership": "exclusive", "usage_count": 1, "proof_revision": proof_revision},
        {
            "resource_type": "fileset",
            "resource_name": fileset or job_name,
            "ownership": "exclusive" if fileset and sum(1 for text in job_refs if _resource_key(text, "FileSet") == fileset) == 1 else "shared" if fileset else "unknown",
            "usage_count": sum(1 for text in job_refs if fileset and _resource_key(text, "FileSet") == fileset),
            "proof_revision": proof_revision,
        },
        {
            "resource_type": "pool",
            "resource_name": pool or state["vm"],
            "ownership": "exclusive" if pool and sum(1 for text in job_refs if _resource_key(text, "Pool") == pool) == 1 else "shared" if pool else "unknown",
            "usage_count": sum(1 for text in job_refs if pool and _resource_key(text, "Pool") == pool),
            "proof_revision": proof_revision,
        },
    ]
    if state["definition"]["trigger_mode"] == "calendar":
        usage = sum(1 for text in job_refs if _resource_key(text, "Schedule") == schedule_name)
        rows.append(
            {
                "resource_type": "schedule",
                "resource_name": schedule_name,
                "ownership": "exclusive" if usage == 1 else "shared" if usage else "unknown",
                "usage_count": usage,
                "proof_revision": proof_revision,
            }
        )
    return rows


def _dependency_rows(policy, state, proof_revision: int):
    rows = []
    definitions = {}
    for name in sorted(policy.NAMES):
        job_path = policy.paths(name)[0]
        if job_path.exists():
            definition = policy.policy_marker(job_path.read_text())
            if definition:
                definitions[_job_name(name)] = definition
    target = _job_name(state["vm"])
    for job_name, definition in definitions.items():
        source = (definition.get("after_job") or {}).get("source_job")
        if job_name == target and source:
            rows.append({"relation": "depends_on", "related_stable_id": source.lower(), "related_job_name": source, "proof_revision": proof_revision})
        elif source == target:
            rows.append({"relation": "required_by", "related_stable_id": job_name.lower(), "related_job_name": job_name, "proof_revision": proof_revision})
    return rows


def _unmanaged_coverage_rows(state, proof_revision: int):
    target = _job_name(state["vm"])
    rows = []
    for name, text in state["all_jobs"].items():
        if name in state["jobs"]:
            continue
        if target in text and ("Run Before Job" in text or "Run After Job" in text or f"dependency trigger begin: {target}" in text):
            rows.append({"kind": "coverage", "summary": f"Unmanaged job definition {name} references {target}; inbound runtime coverage is not yet authoritative.", "proof_revision": proof_revision})
    if re.search(r"^\s*JobDefs\s*=\s*(\S+)", state["job_text"], re.M):
        rows.append({"kind": "coverage", "summary": f"{target} inherits JobDefs and runtime include coverage is not yet authoritative.", "proof_revision": proof_revision})
    return rows


def _list_active_catalog_operations(job_name: str):
    policy = _load_policy_module()
    try:
        policy.active()
        return [], True
    except ValueError as exc:
        return [{"operation_id": "catalog-active", "kind": "backup", "state": "active", "summary": str(exc)}], True


def _scan_receipts(job_name: str, *, exclude_request_id: str | None = None):
    rows = []
    if ROOT.exists():
        for path in sorted(ROOT.glob("*.json")):
            if path.name.endswith(".before.json"):
                continue
            payload = json.loads(path.read_text())
            if payload.get("jobName") != job_name:
                continue
            if exclude_request_id and payload.get("id") == exclude_request_id:
                continue
            if payload.get("state") in UNRESOLVED_RECEIPT_STATES:
                rows.append({"kind": "maintenance", "summary": f"Lifecycle receipt {payload['id']} is still {payload['state']}.", "proof_revision": payload.get("proofRevision")})
    runtime_root = _after_job_runtime_state_dir() / "receipts"
    if runtime_root.exists():
        for path in sorted(runtime_root.glob("*.json")):
            payload = json.loads(path.read_text())
            if payload.get("target") != job_name and payload.get("source") != job_name:
                continue
            if payload.get("state") in {"Prepared", "Deferred", "Dispatching", "Queued", "Unknown"}:
                rows.append({"kind": "runtime", "summary": f"After-job runtime receipt for {job_name} is still {payload['state']}.", "proof_revision": payload.get("proofRevision")})
    return rows


def _proof_payload(policy, state):
    active_operations, operations_complete = _list_active_catalog_operations(_job_name(state["vm"]))
    unresolved = _scan_receipts(_job_name(state["vm"]))
    proof = {
        "jobName": _job_name(state["vm"]),
        "definition": state["definition"],
        "lifecycleState": state["lifecycle_state"],
        "jobDigest": hashlib.sha256(state["job_text"].encode()).hexdigest(),
        "poolDigest": hashlib.sha256(state["pool_text"].encode()).hexdigest(),
        "scheduleDigest": hashlib.sha256((state["schedule_text"] or "").encode()).hexdigest(),
        "triggerDigest": hashlib.sha256(policy.TRIGGER.read_text().encode()).hexdigest() if policy.TRIGGER.exists() else None,
        "activeOperations": active_operations,
        "activeOperationsComplete": operations_complete,
        "unresolvedIntents": unresolved,
        "resources": [],
        "dependencies": [],
    }
    revision = int(_sha(proof)[:12], 16) % 1_000_000_000 or 1
    proof["resources"] = _resource_rows(policy, state, revision)
    proof["dependencies"] = _dependency_rows(policy, state, revision)
    proof["coverageGaps"] = _unmanaged_coverage_rows(state, revision)
    for row in proof["activeOperations"]:
        row["proof_revision"] = revision
    for row in proof["unresolvedIntents"]:
        row["proof_revision"] = revision
    proof["proofRevision"] = revision
    proof["proofCoverage"] = ["resources", "dependencies", "intents"] + (["operations"] if operations_complete else [])
    proof["currentDigest"] = _sha({k: v for k, v in proof.items() if k != "currentDigest"})
    return proof


def current(job_name: str):
    transport_ready()
    policy = _load_policy_module()
    state = _lifecycle_state(policy, job_name)
    proof = _proof_payload(policy, state)
    blockers = []
    for row in proof["activeOperations"]:
        blockers.append({"code": "active_operation", "summary": row["summary"]})
    for row in proof["unresolvedIntents"]:
        blockers.append({"code": "runtime_pending", "summary": row["summary"]})
    if "operations" not in proof["proofCoverage"]:
        blockers.append({"code": "missing_operation_proof", "summary": "Active Catalog operation proof is unavailable."})
    for row in proof.get("coverageGaps", []):
        blockers.append({"code": "unmanaged_runtime_coverage_unproven", "summary": row["summary"]})
    return {
        "jobName": job_name,
        "definition": state["definition"],
        "lifecycleState": state["lifecycle_state"],
        "resources": proof["resources"],
        "dependencies": proof["dependencies"],
        "operations": proof["activeOperations"],
        "unresolvedIntents": proof["unresolvedIntents"],
        "proofCoverage": proof["proofCoverage"],
        "proofRevision": proof["proofRevision"],
        "currentDigest": proof["currentDigest"],
        "blockers": blockers,
        "executionReady": not blockers,
        "readiness": "candidate_ready" if not blockers else "blocked",
    }


def review(action: str, job_name: str, definition: dict | None = None):
    current_state = current(job_name)
    if current_state["blockers"]:
        raise ValueError(current_state["blockers"][0]["summary"])
    chosen_definition = definition or current_state["definition"]
    if action == "disable":
        _require(current_state["lifecycleState"] == "enabled", "Job is already in disabled lifecycle state.")
    elif action == "enable":
        _require(definition is not None, "Enable review requires the reviewed managed definition.")
        _require(current_state["lifecycleState"] == "disabled", "Job is not currently in disabled lifecycle state.")
    else:
        raise ValueError("Unsupported lifecycle review action.")
    body = {
        "action": action,
        "jobName": job_name,
        "proofRevision": current_state["proofRevision"],
        "currentDigest": current_state["currentDigest"],
        "definition": chosen_definition,
    }
    return {
        **body,
        "reviewDigest": _sha(body),
        "current": current_state,
    }


def _disable_writes(policy, state):
    definition = state["definition"]
    updated_job = policy.set_directive(state["job_text"], "Schedule", None)
    updated_job = policy.set_directive(updated_job, "Reschedule On Error", "no")
    updated_job = policy.set_directive(updated_job, "Reschedule Times", None)
    updated_job = policy.set_directive(updated_job, "Reschedule Interval", None)
    updated_job = policy.set_directive(updated_job, "Rerun Failed Levels", None)
    updated_job = policy.set_marker(updated_job, definition)
    rows = [(state["job_path"], updated_job)]
    if definition["trigger_mode"] == "after_job":
        source = definition["after_job"]["source_job"][7:]
        source_path = policy.paths(source)[0]
        rows.append((source_path, policy.drop_dependency_block(source_path.read_text(), _job_name(state["vm"]))))
    return rows


def _enable_writes(policy, state, definition):
    job_text = policy.drop_dependency_block(state["job_text"], _job_name(state["vm"]))
    job_text = policy.set_directive(job_text, "Reschedule On Error", "yes" if definition["retry_count"] else "no")
    job_text = policy.set_directive(job_text, "Reschedule Times", str(definition["retry_count"]) if definition["retry_count"] else None)
    job_text = policy.set_directive(job_text, "Reschedule Interval", str(definition["retry_interval_minutes"] * 60) if definition["retry_count"] else None)
    job_text = policy.set_directive(job_text, "Rerun Failed Levels", "yes" if definition["retry_count"] else None)
    job_text = policy.set_marker(job_text, definition)
    rows = []
    if definition["trigger_mode"] == "calendar":
        schedule_name = state["schedule_path"].stem
        job_text = policy.set_directive(job_text, "Schedule", schedule_name)
        rows.append((state["schedule_path"], policy.calendar_schedule(schedule_name, definition["time_wita"], definition["automatic"], definition.get("calendar"), definition.get("window_end_wita"))))
    else:
        job_text = policy.set_directive(job_text, "Schedule", None)
        source_path = policy.paths(definition["after_job"]["source_job"][7:])[0]
        rows.append((source_path, policy.add_dependency_block(source_path.read_text(), _job_name(state["vm"]), definition)))
        rows.append((state["schedule_path"], None))
    rows.append((state["job_path"], job_text))
    return rows


def _lock():
    mod = _load_lock_module()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    stream = open(LOCK, "a", encoding="utf-8")
    mod.flock(stream.fileno(), mod.LOCK_EX | mod.LOCK_NB)
    return stream


def _runtime_lock(job_name: str):
    mod = _load_lock_module()
    path = _runtime_lock_path(job_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(path, "a+", encoding="utf-8")
    mod.flock(stream.fileno(), mod.LOCK_EX | mod.LOCK_NB)
    return stream


def _receipt_paths(request_id: str):
    return ROOT / f"{request_id}.json", ROOT / f"{request_id}.before.json"


def _update_receipt(path: Path, payload: dict):
    _write_json_atomic(path, payload)
    path.chmod(0o600)


def _require_root():
    _require(hasattr(os, "geteuid") and os.geteuid() == 0, "Root-owned native lifecycle execution is required.")


def apply(body: dict):
    _require_root()
    transport_ready()
    request_id = str(UUID(body["request_id"]))
    actor = body["actor"]
    action = body["action"]
    job_name = body["job_name"]
    definition = body.get("definition")
    ROOT.mkdir(mode=0o700, exist_ok=True)
    receipt_path, before_path = _receipt_paths(request_id)
    with contextlib.ExitStack() as stack:
        stack.enter_context(_lock())
        stack.enter_context(_runtime_lock(job_name))
        if receipt_path.exists():
            saved = json.loads(receipt_path.read_text())
            _require(
                saved["actor"] == actor
                and saved["action"] == action
                and saved["jobName"] == job_name
                and saved["proofRevision"] == body["proof_revision"]
                and saved["reviewDigest"] == body["digest"]
                and saved.get("definition") == definition,
                "Request key belongs to another lifecycle intent.",
            )
            return saved
        reviewed = review(action, job_name, definition)
        _require(reviewed["reviewDigest"] == body["digest"], "Lifecycle intent changed since review. Review again.")
        _require(reviewed["proofRevision"] == body["proof_revision"], "Lifecycle proof changed since review. Refresh and review again.")
        _require(not reviewed["current"]["operations"], reviewed["current"]["operations"][0]["summary"] if reviewed["current"]["operations"] else "")
        _require(not reviewed["current"]["unresolvedIntents"], reviewed["current"]["unresolvedIntents"][0]["summary"] if reviewed["current"]["unresolvedIntents"] else "")
        policy = _load_policy_module()
        state = _lifecycle_state(policy, job_name)
        source = (state["definition"].get("after_job") or {}).get("source_job")
        if source and source.startswith("VMware-"):
            stack.enter_context(_runtime_lock(source))
        writes = _disable_writes(policy, state) if action == "disable" else _enable_writes(policy, state, reviewed["definition"])
        before = {
            "id": request_id,
            "jobName": job_name,
            "paths": [{"path": str(path), "before": _read_text(path)} for path, _ in writes],
        }
        _update_receipt(
            receipt_path,
            {
                "id": request_id,
                "actor": actor,
                "action": action,
                "jobName": job_name,
                "proofRevision": body["proof_revision"],
                "reviewDigest": body["digest"],
                "definition": reviewed["definition"],
                "state": "Prepared",
                "beforeImagesPath": str(before_path),
            },
        )
        _write_json_atomic(before_path, before)
        before_path.chmod(0o600)
        _update_receipt(
            receipt_path,
            {
                "id": request_id,
                "actor": actor,
                "action": action,
                "jobName": job_name,
                "proofRevision": body["proof_revision"],
                "reviewDigest": body["digest"],
                "definition": reviewed["definition"],
                "state": "Dispatching",
                "beforeImagesPath": str(before_path),
            },
        )
        try:
            for path, after in writes:
                if after is None:
                    path.unlink(missing_ok=True)
                else:
                    policy.write(path, after)
            policy.syntax()
            policy.console("reload")
            reread = current(job_name)
            expected_state = "disabled" if action == "disable" else "enabled"
            _require(reread["lifecycleState"] == expected_state, "Lifecycle read-back did not reach the reviewed state.")
            if action == "enable":
                _require(reread["definition"] == reviewed["definition"], "Managed definition did not round-trip after enable.")
            else:
                _require(reread["definition"] == state["definition"], "Disable must preserve the stored managed definition marker.")
            result = {
                "id": request_id,
                "actor": actor,
                "action": action,
                "jobName": job_name,
                "proofRevision": body["proof_revision"],
                "reviewDigest": body["digest"],
                "definition": reviewed["definition"],
                "state": "Applied",
                "beforeImagesPath": str(before_path),
                "afterProofRevision": reread["proofRevision"],
            }
            _update_receipt(receipt_path, result)
            return result
        except Exception:
            before_images = json.loads(before_path.read_text())["paths"]
            for row in reversed(before_images):
                previous = row["before"]
                path = Path(row["path"])
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    policy.write(path, previous)
            try:
                policy.syntax()
                policy.console("reload")
                result = {
                    "id": request_id,
                    "actor": actor,
                    "action": action,
                    "jobName": job_name,
                    "proofRevision": body["proof_revision"],
                    "reviewDigest": body["digest"],
                    "definition": reviewed["definition"],
                    "state": "Failed",
                    "beforeImagesPath": str(before_path),
                    "message": "Lifecycle apply failed; original configuration restored.",
                }
            except Exception:
                result = {
                    "id": request_id,
                    "actor": actor,
                    "action": action,
                    "jobName": job_name,
                    "proofRevision": body["proof_revision"],
                    "reviewDigest": body["digest"],
                    "definition": reviewed["definition"],
                    "state": "Unknown",
                    "beforeImagesPath": str(before_path),
                    "message": "Lifecycle rollback unconfirmed. Inspect the root receipt before another change.",
                }
            _update_receipt(receipt_path, result)
            return result


def status(request_id: str):
    return json.loads((_receipt_paths(str(UUID(request_id)))[0]).read_text())


if __name__ == "__main__":
    try:
        body = json.load(sys.stdin)
        action = body["action"]
        if action == "capabilities":
            result = capabilities()
        elif action == "current":
            result = current(body["job_name"])
        elif action == "review":
            result = review(body["lifecycle_action"], body["job_name"], body.get("definition"))
        elif action in ("disable", "enable"):
            result = apply(body)
        elif action == "status":
            result = status(body["request_id"])
        else:
            raise ValueError("Unsupported lifecycle action.")
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"error": "Lifecycle helper request failed."}))
        sys.exit(1)
