"""Root-owned native lifecycle resource executor for clone and retirement actions."""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

CONTRACT_VERSION = "lifecycle-native-b6"
CLONE_BINDING_PROTOCOL = "native-clone-binding-v1"
RETIREMENT_BINDING_PROTOCOL = "native-retirement-binding-v1"
ROOT = Path("/etc/bareos")
DIR_BASE = ROOT / "bareos-dir.d"
SD_BASE = ROOT / "bareos-sd.d"
BIN = Path("/opt/bareos/25.1.1/sbin")
RECEIPTS = Path("/var/lib/bareos-lifecycle-resources")
LIFECYCLE_LOCK = Path("/var/lib/bareos/vm-chain-retention.lock")
STORAGE_SECRET_PATH = DIR_BASE / "storage" / "VeeamSMB.conf"
SMB_ROOT = Path("/mnt/bareos-smb")
HELPER_RECEIPTS = Path("/var/lib/bareos-lifecycle-applications")
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,59}$")


def _require(ok: bool, message: str):
    if not ok:
        raise ValueError(message)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _json_digest(value: object) -> str:
    return _sha_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def _safe_error(default: str):
    return default


def _load_lock_module():
    try:
        return importlib.import_module("fcntl")
    except ModuleNotFoundError as exc:
        raise RuntimeError("Native lifecycle executor requires POSIX file locking support.") from exc


def _load_onboarding_contract():
    targets = ["integration.onboarding_contract"]
    if __package__ in (None, ""):
        targets.append("onboarding_contract")
    last_exc = None
    for name in targets:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            last_exc = exc
            expected = {name, name.split(".")[-1], "integration"}
            if exc.name not in expected:
                raise RuntimeError(f"Native lifecycle dependency unavailable: {exc.name}.") from exc
    raise RuntimeError("Native lifecycle dependency unavailable: onboarding_contract.") from last_exc


def _hex_digest(value: str, *, field: str):
    _require(isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value)), f"{field} must be a SHA256 digest.")
    return value


def _read_bounded(limit: int = 65536) -> dict:
    data = sys.stdin.buffer.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Request too large.")
    value = json.loads(data or b"{}")
    _require(isinstance(value, dict), "Request body must be a JSON object.")
    return value


def _atomic_write_bytes(path: Path, data: bytes, *, mode: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        _safe_chown(temp_path, "root", "bareos")
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: dict, *, mode: int = 0o600):
    _atomic_write_bytes(path, json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"), mode=mode)


def _fsync_dir(path: Path):
    handle = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def _safe_chown(path: Path, user: str, group: str):
    shutil.chown(path, user, group)


def _lock():
    mod = _load_lock_module()
    LIFECYCLE_LOCK.parent.mkdir(parents=True, exist_ok=True)
    stream = open(LIFECYCLE_LOCK, "a+", encoding="utf-8")
    mod.flock(stream.fileno(), mod.LOCK_EX | mod.LOCK_NB)
    return stream


def _after_job_runtime_state_dir() -> Path:
    return Path(os.environ.get("BACKUPCENTER_AFTER_JOB_STATE", "/var/lib/bareos-after-job-runtime"))


def _runtime_lock_path(job_name: str) -> Path:
    return _after_job_runtime_state_dir() / "locks" / f"{job_name}.target.lock"


def _runtime_lock(job_name: str):
    mod = _load_lock_module()
    path = _runtime_lock_path(job_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = open(path, "a+", encoding="utf-8")
    mod.flock(stream.fileno(), mod.LOCK_EX | mod.LOCK_NB)
    return stream


def _cmd(args: list[str], *, input: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input, text=True, capture_output=True, timeout=timeout, check=False)


def _secure_owned_path(path: Path, *, allow_missing: bool = False):
    if path.is_symlink():
        raise ValueError("Lifecycle native path cannot be a symlink.")
    if allow_missing and not path.exists():
        return
    state = path.stat()
    if state.st_uid != 0 or state.st_mode & 0o022:
        raise ValueError("Lifecycle helper requires an administrator-owned path.")


def _secure_owned_parent_chain(path: Path):
    current = path
    while True:
        _secure_owned_path(current)
        if current == current.parent:
            break
        current = current.parent
        if current == Path("/") or re.fullmatch(r"[A-Za-z]:\\\\?", str(current)):
            break


def _helper_hash(path: Path) -> str | None:
    return _sha_bytes(path.read_bytes()) if path.exists() else None


def _storage_secret() -> str:
    _secure_owned_path(STORAGE_SECRET_PATH)
    match = re.search(r"^\s*Password\s*=\s*(.+)$", STORAGE_SECRET_PATH.read_text(), re.M)
    _require(bool(match), "Existing Storage secret is unavailable.")
    return match.group(1)


def _scan_unresolved_receipts(job_name: str) -> list[dict]:
    rows = []
    if HELPER_RECEIPTS.exists():
        for path in sorted(HELPER_RECEIPTS.glob("*.json")):
            if path.name.endswith(".before.json"):
                continue
            payload = json.loads(path.read_text())
            if payload.get("jobName") == job_name and payload.get("state") in {"Prepared", "Dispatching", "Unknown"}:
                rows.append({"kind": "lifecycle", "state": payload["state"]})
    runtime_root = _after_job_runtime_state_dir() / "receipts"
    if runtime_root.exists():
        for path in sorted(runtime_root.glob("*.json")):
            payload = json.loads(path.read_text())
            if payload.get("target") == job_name or payload.get("source") == job_name:
                if payload.get("state") in {"Prepared", "Deferred", "Dispatching", "Queued", "Unknown"}:
                    rows.append({"kind": "runtime", "state": payload["state"]})
    return rows


def _extract_uuid(fileset_text: str) -> str:
    match = re.search(r":uuid=([0-9a-fA-F-]{36})", fileset_text)
    _require(bool(match), "Clone fileset does not contain one exact VM UUID.")
    return str(UUID(match.group(1)))


def _manualized_job(text: str) -> str:
    rows = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("Schedule ="):
            continue
        if stripped == "Enabled = yes":
            rows.append(" Enabled = no")
            continue
        rows.append(raw)
    return "\n".join(rows) + "\n"


def _clone_paths(label: str) -> dict[str, Path]:
    return {
        "storage": DIR_BASE / "storage" / f"{label}.conf",
        "device": SD_BASE / "device" / f"{label}.conf",
        "pool": DIR_BASE / "pool" / f"{label}.conf",
        "fileset": DIR_BASE / "fileset" / f"{label}.conf",
        "job": DIR_BASE / "job" / f"{label}.conf",
        "folder": SMB_ROOT / label,
    }


def _capture_before(paths: list[Path], intent_id: str) -> dict:
    before_path = RECEIPTS / "before-images" / f"{intent_id}.json"
    rows = []
    for path in paths:
        rows.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "mode": stat.S_IMODE(path.stat().st_mode) if path.exists() else None,
                "digest": _sha_bytes(path.read_bytes()) if path.exists() and path.is_file() else None,
                "content": base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() and path.is_file() else None,
            }
        )
    payload = {"beforeImageRef": str(before_path), "paths": rows}
    _atomic_write_json(before_path, payload)
    return payload


def _restore_before(before: dict):
    for row in reversed(before["paths"]):
        path = Path(row["path"])
        if not row["exists"]:
            _require(not path.exists() or path.is_file(), "Unexpected native path type during rollback.")
            path.unlink(missing_ok=True)
            continue
        content = base64.b64decode(row["content"].encode("ascii"))
        _atomic_write_bytes(path, content, mode=row["mode"] or 0o640)


def _job_readback(job_name: str) -> bool:
    result = _cmd([str(BIN / "bconsole")], input=f"show job={job_name}\nquit\n", timeout=45)
    transcript = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.returncode == 0 and f'Name = "{job_name}"' in transcript


def _job_absent_readback(job_name: str) -> bool:
    result = _cmd([str(BIN / "bconsole")], input=f"show job={job_name}\nquit\n", timeout=45)
    transcript = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.returncode == 0 and f'Name = "{job_name}"' not in transcript


def _storage_readback(storage_name: str) -> bool:
    result = _cmd([str(BIN / "bconsole")], input=f"show storage={storage_name}\nquit\n", timeout=45)
    transcript = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.returncode == 0 and (storage_name in transcript or not transcript)


def _syntax_and_reload():
    checks = [
        _cmd(["runuser", "-u", "bareos", "--", str(BIN / "bareos-dir"), "-t"], timeout=45),
        _cmd([str(BIN / "bareos-sd"), "-t"], timeout=45),
        _cmd([str(BIN / "bconsole")], input="reload\nquit\n", timeout=45),
    ]
    _require(all(row.returncode == 0 for row in checks), "Native Bareos validation or reload failed.")


def _secure_paths_ready() -> bool:
    try:
        _secure_owned_path(ROOT)
        _secure_owned_path(DIR_BASE)
        _secure_owned_path(SD_BASE)
        _secure_owned_path(STORAGE_SECRET_PATH)
        _secure_owned_path(RECEIPTS.parent, allow_missing=True)
        _secure_owned_path(LIFECYCLE_LOCK.parent)
        _secure_owned_path(SMB_ROOT.parent, allow_missing=True)
        return True
    except Exception:
        return False


def _onboarding_contract_hash() -> str | None:
    contract = _load_onboarding_contract()
    path = Path(contract.__file__).resolve()
    return _helper_hash(path)


def _binding_digest(payload: dict, fields: tuple[str, ...]) -> str:
    return _json_digest({field: payload.get(field) for field in fields})


def _trusted_receipt_path(path_value: str, *, folder: str) -> Path:
    path = Path(path_value)
    _require(not path.is_symlink(), "Opaque native receipt path is not trusted.")
    root = (RECEIPTS / folder).resolve()
    resolved = path.resolve()
    _require(resolved.is_relative_to(root), "Opaque native receipt path is outside the trusted receipt root.")
    return resolved


def _retirement_receipt_path(intent_id: str, action: str) -> Path:
    return RECEIPTS / f"retirement-{action}" / f"{intent_id}.json"


def describe_capabilities() -> dict:
    helper_path = Path("/opt/bareos-api/apply_job_lifecycle.py")
    executor_path = Path(__file__).resolve()
    blocker = None
    installed = False
    root_ready = hasattr(os, "geteuid") and os.geteuid() == 0
    locks_ready = False
    try:
        _load_lock_module()
        with _lock():
            locks_ready = True
    except Exception:
        blocker = _safe_error("Native lifecycle locking is unavailable.")
    try:
        contract = _load_onboarding_contract()
        policy_version = getattr(contract, "POLICY", "unknown")
        onboarding_hash = _onboarding_contract_hash()
    except Exception:
        contract_version = "unknown"
        policy_version = "unknown"
        onboarding_hash = None
        blocker = blocker or _safe_error("Native lifecycle dependencies are unavailable.")
    secure_paths_ready = _secure_paths_ready()
    prereqs = {
        "pythonReady": Path(sys.executable).exists(),
        "configRootReady": ROOT.exists(),
        "bareosDirReady": (BIN / "bareos-dir").exists(),
        "bareosSdReady": (BIN / "bareos-sd").exists(),
        "bconsoleReady": (BIN / "bconsole").exists(),
        "storageSecretReady": STORAGE_SECRET_PATH.exists(),
        "rootReady": root_ready,
        "locksReady": locks_ready,
        "securePathsReady": secure_paths_ready,
    }
    prereqs_complete = all(prereqs.values())
    if prereqs_complete:
        installed = True
    if not installed and blocker is None:
        blocker = _safe_error("Native lifecycle prerequisites are not fully installed.")
    return {
        "contractVersion": CONTRACT_VERSION,
        "helperHash": _helper_hash(helper_path),
        "resourceExecutorHash": _helper_hash(executor_path),
        "onboardingContractHash": onboarding_hash,
        "installedReady": installed,
        "transportReady": True,
        "rootReady": root_ready,
        "locksReady": locks_ready,
        "securePathsReady": secure_paths_ready,
        "prerequisitesComplete": prereqs_complete,
        "prerequisites": prereqs,
        "blocker": blocker,
        "policyVersion": policy_version,
        "pythonVersion": sys.version.split()[0],
    }


def _validate_clone_candidate(native_candidate: dict, *, actor: str) -> tuple[str, str, dict, dict[str, Path], dict]:
    _require(isinstance(native_candidate, dict), "Clone native candidate must be a dictionary.")
    _require(native_candidate.get("automaticSchedule") is False and native_candidate.get("enabled") is False, "Clone candidate must stay disabled and manual.")
    _require(native_candidate.get("historyCopied") is False and native_candidate.get("secretsCopied") is False, "Clone candidate must not copy history or secrets.")
    plan = native_candidate.get("resourcePlan")
    _require(isinstance(plan, dict), "Clone native candidate must include the reviewed resource plan.")
    label = str(plan.get("pool") or "")
    _require(bool(SAFE_LABEL.fullmatch(label)), "Clone resource label is invalid.")
    paths = _clone_paths(label)
    expected_keys = {f"bareos-dir.d/{kind}/{label}.conf" for kind in ("storage", "pool", "fileset", "job")} | {f"bareos-sd.d/device/{label}.conf"}
    files = plan.get("files")
    _require(isinstance(files, dict) and set(files) == expected_keys, "Clone files must match the canonical reviewed Bareos resource set.")
    uuid_value = _extract_uuid(str(files[f"bareos-dir.d/fileset/{label}.conf"]))
    expected = _load_onboarding_contract().build(uuid_value, label)
    expected_files = dict(expected["files"])
    expected_files[f"bareos-dir.d/job/{label}.conf"] = _manualized_job(expected_files[f"bareos-dir.d/job/{label}.conf"])
    _require(plan.get("job") == expected["job"], "Clone job name does not match the canonical reviewed onboarding resources.")
    _require(plan.get("storage") == expected["storage"] and plan.get("fileset") == expected["fileset"], "Clone resources do not match the canonical onboarding contract.")
    _require(plan.get("folder") == expected["folder"], "Clone target SMB folder is not canonical.")
    _require(files == expected_files, "Clone file contents differ from the reviewed canonical onboarding resources.")
    _require(native_candidate.get("resourceDigest") == _json_digest(plan), "Clone resource digest drifted since review.")
    _require(native_candidate.get("candidateDigest") == _json_digest({k: native_candidate[k] for k in ("automaticSchedule", "enabled", "historyCopied", "secretsCopied", "resourcePlan")}), "Clone candidate digest drifted since review.")
    binding = native_candidate.get("binding")
    _require(isinstance(binding, dict), "Clone native binding proof is unavailable.")
    _require(binding.get("protocol") == CLONE_BINDING_PROTOCOL, "Clone native binding protocol is unsupported.")
    _require(binding.get("contractVersion") == CONTRACT_VERSION, "Clone native binding contract is stale.")
    _require(binding.get("complete") is True, "Clone native binding proof is incomplete.")
    _require(binding.get("actor") == actor, "Clone native binding actor does not match the reviewed request.")
    _require(binding.get("targetJobName") == plan["job"], "Clone native binding job name does not match the reviewed candidate.")
    _require(binding.get("targetVmUuid") == uuid_value, "Clone native binding VM identity does not match the reviewed candidate.")
    _require(binding.get("resourceLabel") == label, "Clone native binding label does not match the reviewed candidate.")
    _require(isinstance(binding.get("repositoryId"), str) and bool(binding["repositoryId"].strip()), "Clone native repository proof is unavailable.")
    _require(binding.get("candidateDigest") == native_candidate["candidateDigest"], "Clone native binding candidate digest drifted since review.")
    _require(binding.get("resourceDigest") == native_candidate["resourceDigest"], "Clone native binding resource digest drifted since review.")
    _hex_digest(str(binding.get("reviewDigest") or ""), field="Clone binding reviewDigest")
    _require(isinstance(binding.get("proofRevision"), int) and binding["proofRevision"] > 0, "Clone native binding proof revision is invalid.")
    coverage = binding.get("proofCoverage")
    _require(isinstance(coverage, list) and set(coverage) >= {"registry", "collector", "store", "inventory"}, "Clone native binding proof coverage is incomplete.")
    binding_fields = ("protocol", "contractVersion", "complete", "actor", "targetJobName", "targetVmUuid", "resourceLabel", "repositoryId", "candidateDigest", "resourceDigest", "reviewDigest", "proofRevision", "proofCoverage")
    expected_binding_digest = _binding_digest(binding, binding_fields)
    _require(binding.get("bindingDigest") == expected_binding_digest, "Clone native binding hash does not match the reviewed proof.")
    return label, uuid_value, plan, paths, binding


def _clone_receipt_path(intent_id: str) -> Path:
    return RECEIPTS / "clone" / f"{intent_id}.json"


def _clone_result_from_receipt(receipt_path: Path, payload: dict) -> dict:
    return {
        "state": str(payload.get("state") or "Unknown").lower(),
        "summary": payload.get("summary"),
        "nativeReceipt": str(receipt_path),
    }


def apply_clone(native_candidate: dict, *, actor: str, intent_id: str) -> dict:
    _require(hasattr(os, "geteuid") and os.geteuid() == 0, "Root-owned clone execution is required.")
    _require(bool(actor), "Clone actor is required.")
    rid = str(UUID(intent_id))
    with _lock():
        receipt_path = _clone_receipt_path(rid)
        if receipt_path.exists():
            payload = json.loads(receipt_path.read_text())
            _require(payload["actor"] == actor and payload["candidateDigest"] == native_candidate.get("candidateDigest"), "Request key belongs to another clone intent.")
            return _clone_result_from_receipt(receipt_path, payload)
        label, _, plan, paths, binding = _validate_clone_candidate(native_candidate, actor=actor)
        _require(not _scan_unresolved_receipts(plan["job"]), "Clone target has unresolved lifecycle or runtime receipts.")
        _secure_owned_path(ROOT)
        for path in paths.values():
            if path != paths["folder"]:
                _secure_owned_path(path.parent)
        folder = paths["folder"]
        _require(not folder.is_symlink(), "Clone target folder cannot be a symlink.")
        _require((not folder.exists()) or (folder.is_dir() and not any(folder.iterdir())), "Clone target folder must be dedicated and empty.")
        for key, path in paths.items():
            if key == "folder":
                continue
            _require(not path.exists(), "Clone target resources already exist and require reconciliation.")
        before = _capture_before([path for key, path in paths.items() if key != "folder"], rid)
        with _runtime_lock(plan["job"]):
            receipt = {
                "id": rid,
                "actor": actor,
                "state": "Dispatching",
                "jobName": plan["job"],
                "candidateDigest": native_candidate["candidateDigest"],
                "bindingDigest": binding["bindingDigest"],
                "beforeImageRef": before["beforeImageRef"],
            }
            _atomic_write_json(receipt_path, receipt)
            secret = _storage_secret()
            try:
                folder.mkdir(parents=True, exist_ok=False)
                _safe_chown(folder, "bareos", "bareos")
                for rel, text in plan["files"].items():
                    target = ROOT / rel
                    _atomic_write_bytes(target, text.replace('"<existing-storage-secret>"', secret).encode("utf-8"), mode=0o640)
                _syntax_and_reload()
                _require(_job_readback(plan["job"]), "Director did not confirm the reviewed cloned job.")
                _require(_storage_readback(plan["storage"]), "Storage daemon did not confirm the reviewed cloned storage.")
                applied = {
                    **receipt,
                    "state": "Applied",
                    "summary": "Clone candidate was written to native resources and confirmed by Director and Storage read-back.",
                }
                _atomic_write_json(receipt_path, applied)
                return _clone_result_from_receipt(receipt_path, applied)
            except Exception:
                try:
                    _restore_before(before)
                    if folder.exists() and not any(folder.iterdir()):
                        folder.rmdir()
                    _syntax_and_reload()
                    failed = {
                        **receipt,
                        "state": "Failed",
                        "summary": "Clone native apply failed and the original resources were restored.",
                    }
                    _atomic_write_json(receipt_path, failed)
                    return _clone_result_from_receipt(receipt_path, failed)
                except Exception:
                    unknown = {
                        **receipt,
                        "state": "Unknown",
                        "summary": "Clone native outcome is unknown. Reconcile the root receipt and resource files before another request.",
                    }
                    _atomic_write_json(receipt_path, unknown)
                    return _clone_result_from_receipt(receipt_path, unknown)


def _canonical_job_path(job_name: str) -> Path:
    _require(job_name.startswith("VMware-"), "Only managed VMware job names are supported.")
    label = job_name[7:]
    _require(bool(SAFE_LABEL.fullmatch(label)), "Managed job label is invalid.")
    path = DIR_BASE / "job" / f"{label}.conf"
    _require(path.resolve().parent == (DIR_BASE / "job").resolve(), "Managed job path is outside the canonical Bareos job directory.")
    return path


def _retire_beforeimage(job_name: str, path: Path, data: bytes, *, actor: str | None, intent_id: str | None, review_digest: str | None) -> dict:
    opaque = RECEIPTS / "retirement-before" / f"{job_name}-{uuid4()}.json"
    payload = {
        "opaqueRef": str(opaque),
        "protocol": RETIREMENT_BINDING_PROTOCOL,
        "contractVersion": CONTRACT_VERSION,
        "jobName": job_name,
        "path": str(path),
        "digest": _sha_bytes(data),
        "actor": actor,
        "intentId": intent_id,
        "reviewDigest": review_digest,
        "content": base64.b64encode(data).decode("ascii"),
    }
    _atomic_write_json(opaque, payload)
    return payload


def _retirement_binding(actor: str | None, intent_id: str | None, review_digest: str | None) -> tuple[str, str, str]:
    _require(bool(actor), "Retirement native mutation is unsupported without a bound actor.")
    _require(bool(intent_id), "Retirement native mutation is unsupported without a bound intent.")
    _require(bool(review_digest), "Retirement native mutation is unsupported without a bound review digest.")
    rid = str(UUID(str(intent_id)))
    digest = _hex_digest(str(review_digest), field="Retirement reviewDigest")
    return str(actor), rid, digest


def capture_job_config(job_name: str, *, actor: str | None = None, intent_id: str | None = None, review_digest: str | None = None) -> dict:
    _require(hasattr(os, "geteuid") and os.geteuid() == 0, "Root-owned retirement capture is required.")
    path = _canonical_job_path(job_name)
    _secure_owned_path(path)
    data = path.read_bytes()
    opaque = _retire_beforeimage(job_name, path, data, actor=actor, intent_id=intent_id, review_digest=review_digest)
    return {
        "path": str(path),
        "digest": _sha_bytes(data),
        "exists": True,
        "opaqueRef": opaque["opaqueRef"],
        "actor": actor,
        "intentId": intent_id,
        "reviewDigest": review_digest,
    }


def delete_job_config(
    job_name: str,
    *,
    expected_path: str,
    expected_digest: str,
    actor: str | None = None,
    intent_id: str | None = None,
    review_digest: str | None = None,
) -> dict:
    _require(hasattr(os, "geteuid") and os.geteuid() == 0, "Root-owned retirement delete is required.")
    actor_value, rid, digest = _retirement_binding(actor, intent_id, review_digest)
    path = _canonical_job_path(job_name)
    _require(str(path) == expected_path, "Retirement path does not match the reviewed job configuration.")
    _secure_owned_path(path)
    receipt_path = _retirement_receipt_path(rid, "delete")
    with _lock(), _runtime_lock(job_name):
        if receipt_path.exists():
            payload = json.loads(receipt_path.read_text())
            _require(payload["actor"] == actor_value and payload["jobName"] == job_name and payload["reviewDigest"] == digest, "Request key belongs to another retirement delete intent.")
            return {"path": str(path), "deleted": payload["state"] == "Deleted", "digest": payload["digest"], "opaqueRef": payload["opaqueRef"]}
        _require(not _scan_unresolved_receipts(job_name), "Retirement target has unresolved lifecycle or runtime receipts.")
        _require(path.exists(), "Managed job configuration is already absent.")
        current = path.read_bytes()
        _require(_sha_bytes(current) == expected_digest, "Retirement job configuration digest changed since review.")
        before = _retire_beforeimage(job_name, path, current, actor=actor_value, intent_id=rid, review_digest=digest)
        receipt = {
            "id": rid,
            "protocol": RETIREMENT_BINDING_PROTOCOL,
            "actor": actor_value,
            "jobName": job_name,
            "reviewDigest": digest,
            "digest": expected_digest,
            "opaqueRef": before["opaqueRef"],
            "state": "Dispatching",
        }
        _atomic_write_json(receipt_path, receipt)
        path.unlink()
        _fsync_dir(path.parent)
        _syntax_and_reload()
        _require(_job_absent_readback(job_name), "Director still reports the reviewed job after retirement delete.")
        deleted = {**receipt, "state": "Deleted"}
        _atomic_write_json(receipt_path, deleted)
        return {"path": str(path), "deleted": True, "digest": expected_digest, "opaqueRef": before["opaqueRef"]}


def read_job_config(job_name: str) -> dict:
    path = _canonical_job_path(job_name)
    if not path.exists():
        return {"path": str(path), "exists": False, "digest": None}
    _secure_owned_path(path)
    data = path.read_bytes()
    return {"path": str(path), "exists": True, "digest": _sha_bytes(data)}


def restore_job_config(
    beforeimage: dict,
    *,
    actor: str | None = None,
    intent_id: str | None = None,
    review_digest: str | None = None,
    expected_destination_digest: str | None = None,
) -> dict:
    _require(hasattr(os, "geteuid") and os.geteuid() == 0, "Root-owned retirement restore is required.")
    _require(isinstance(beforeimage, dict) and beforeimage.get("opaqueRef"), "Opaque before-image reference is required.")
    actor_value, rid, digest = _retirement_binding(
        actor or beforeimage.get("actor"),
        intent_id or beforeimage.get("intentId"),
        review_digest or beforeimage.get("reviewDigest"),
    )
    payload = json.loads(_trusted_receipt_path(str(beforeimage["opaqueRef"]), folder="retirement-before").read_text())
    _require(payload.get("protocol") == RETIREMENT_BINDING_PROTOCOL, "Opaque native receipt protocol is unsupported.")
    _require(payload.get("contractVersion") == CONTRACT_VERSION, "Opaque native receipt contract is stale.")
    _require(payload.get("actor") == actor_value, "Opaque native receipt actor does not match the reviewed restore request.")
    _require(payload.get("intentId") == rid, "Opaque native receipt intent does not match the reviewed restore request.")
    _require(payload.get("reviewDigest") == digest, "Opaque native receipt review digest does not match the reviewed restore request.")
    path = Path(payload["path"])
    _require(path == _canonical_job_path("VMware-" + path.stem), "Opaque before-image path is not canonical.")
    current = read_job_config(payload["jobName"])
    if expected_destination_digest is None:
        _require(current["exists"] is False, "Retirement restore requires an explicit destination CAS when the job file already exists.")
    else:
        _hex_digest(str(expected_destination_digest), field="Retirement restore expectedDestinationDigest")
        _require(current["digest"] == expected_destination_digest, "Retirement restore destination digest changed since review.")
    receipt_path = _retirement_receipt_path(rid, "restore")
    with _lock(), _runtime_lock(payload["jobName"]):
        if receipt_path.exists():
            saved = json.loads(receipt_path.read_text())
            _require(saved["actor"] == actor_value and saved["jobName"] == payload["jobName"] and saved["reviewDigest"] == digest, "Request key belongs to another retirement restore intent.")
            return {"path": str(path), "restored": saved["state"] == "Restored", "digest": saved["digest"]}
        receipt = {
            "id": rid,
            "protocol": RETIREMENT_BINDING_PROTOCOL,
            "actor": actor_value,
            "jobName": payload["jobName"],
            "reviewDigest": digest,
            "digest": payload["digest"],
            "opaqueRef": payload["opaqueRef"],
            "state": "Dispatching",
        }
        _atomic_write_json(receipt_path, receipt)
        _atomic_write_bytes(path, base64.b64decode(payload["content"].encode("ascii")), mode=0o640)
        _syntax_and_reload()
        _require(_job_readback(payload["jobName"]), "Director did not confirm the reviewed retirement restore.")
        restored = {**receipt, "state": "Restored"}
        _atomic_write_json(receipt_path, restored)
        return {"path": str(path), "restored": True, "digest": payload["digest"]}


def _dispatch(body: dict) -> dict:
    action = body.get("action")
    if action == "capabilities":
        return describe_capabilities()
    if action == "clone_apply":
        return apply_clone(body["native_candidate"], actor=body["actor"], intent_id=body["intent_id"])
    if action == "retirement_capture":
        return capture_job_config(body["job_name"], actor=body.get("actor"), intent_id=body.get("intent_id"), review_digest=body.get("review_digest"))
    if action == "retirement_delete":
        return delete_job_config(
            body["job_name"],
            expected_path=body["expected_path"],
            expected_digest=body["expected_digest"],
            actor=body.get("actor"),
            intent_id=body.get("intent_id"),
            review_digest=body.get("review_digest"),
        )
    if action == "retirement_read":
        return read_job_config(body["job_name"])
    if action == "retirement_restore":
        return restore_job_config(
            body["beforeimage"],
            actor=body.get("actor"),
            intent_id=body.get("intent_id"),
            review_digest=body.get("review_digest"),
            expected_destination_digest=body.get("expected_destination_digest"),
        )
    raise ValueError("Unsupported native lifecycle action.")


if __name__ == "__main__":
    try:
        with _lock():
            print(json.dumps(_dispatch(_read_bounded())))
    except Exception:
        print(json.dumps({"error": "Native lifecycle request failed."}))
        sys.exit(1)
