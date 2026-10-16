"""Lifecycle helper target adapter."""
from __future__ import annotations

import base64
import importlib
import json
import os
import shlex
import subprocess
from pathlib import Path

REMOTE_WRAPPER = Path(r"C:\Scripts\Projects\bareos\Invoke-BareosRemote.ps1")
REMOTE_APP_ROOT = "/opt/bareos-api"
REMOTE_PYTHON = "/opt/bareos-api-venv/bin/python"
REMOTE_VMWARE_PYTHONPATH = "/opt/bareos/25.1.1/lib/bareos/vmware-python"
REMOTE_LIFECYCLE_HELPER = f"{REMOTE_APP_ROOT}/apply_job_lifecycle.py"
REMOTE_RESOURCE_EXECUTOR = f"{REMOTE_APP_ROOT}/lifecycle_resource_executor.py"
REMOTE_REQUEST_LIMIT = 32768
CONTRACT_VERSION = "lifecycle-native-b6"


def _helper_path():
    return Path(__file__).resolve().parents[1] / "integration" / "apply_job_lifecycle.py"


def _resource_executor_path():
    return Path(__file__).resolve().parents[1] / "integration" / "lifecycle_resource_executor.py"


def _policy_helper_path():
    return Path(__file__).resolve().parents[1] / "integration" / "apply_backup_policy.py"


def _onboarding_contract_path():
    return Path(__file__).resolve().parents[1] / "integration" / "onboarding_contract.py"


def _platform_supported():
    return os.name == "posix"


def _load_helper_module():
    if not _platform_supported():
        raise RuntimeError("Lifecycle helper requires a POSIX Bareos host.")
    try:
        return importlib.import_module("integration.apply_job_lifecycle")
    except ModuleNotFoundError as exc:
        if exc.name not in {"integration", "integration.apply_job_lifecycle"}:
            raise RuntimeError(f"Lifecycle helper dependency unavailable: {exc.name}.") from exc
        raise RuntimeError("Lifecycle helper module is not installed.") from exc


def _load_resource_module():
    if not _platform_supported():
        raise RuntimeError("Lifecycle helper requires a POSIX Bareos host.")
    try:
        return importlib.import_module("integration.lifecycle_resource_executor")
    except ModuleNotFoundError as exc:
        if exc.name not in {"integration", "integration.lifecycle_resource_executor"}:
            raise RuntimeError(f"Lifecycle helper dependency unavailable: {exc.name}.") from exc
        raise RuntimeError("Lifecycle resource executor is not installed.") from exc


def _timeout_for(action: str) -> int:
    return {
        "capabilities": 30000,
        "current": 45000,
        "review": 45000,
        "status": 30000,
        "disable": 120000,
        "enable": 120000,
        "clone_apply": 120000,
        "retirement_capture": 45000,
        "retirement_read": 45000,
        "retirement_delete": 120000,
        "retirement_restore": 120000,
    }.get(action, 45000)


def _remote_script_for(action: str) -> str:
    return REMOTE_RESOURCE_EXECUTOR if action.startswith("clone_") or action.startswith("retirement_") else REMOTE_LIFECYCLE_HELPER


def _remote_command(script: str, body: dict) -> str:
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    if len(raw) > REMOTE_REQUEST_LIMIT:
        raise RuntimeError("Lifecycle request exceeds the bounded transport size.")
    payload = base64.b64encode(raw).decode("ascii")
    return (
        "set -euo pipefail; "
        f"PYTHONPATH={shlex.quote(REMOTE_VMWARE_PYTHONPATH)}${{PYTHONPATH:+:$PYTHONPATH}}; export PYTHONPATH; "
        f"test -x {shlex.quote(REMOTE_PYTHON)}; "
        f"test -f {shlex.quote(script)}; "
        f"printf %s {shlex.quote(payload)} | base64 -d | {shlex.quote(REMOTE_PYTHON)} {shlex.quote(script)}"
    )


def _parse_remote_output(stdout: str) -> dict:
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError("Lifecycle transport returned no payload.")
    line = text.splitlines()[-1]
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Lifecycle transport returned malformed JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Lifecycle transport returned an unexpected payload.")
    if value.get("error"):
        raise RuntimeError("Lifecycle helper rejected the request.")
    return value


def _run_remote(body: dict) -> dict:
    action = str(body.get("action") or "")
    command = _remote_command(_remote_script_for(action), body)
    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REMOTE_WRAPPER),
                "-Root",
                "-Command",
                command,
            ],
            text=True,
            capture_output=True,
            timeout=_timeout_for(action) / 1000,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Lifecycle transport wrapper is unavailable on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Lifecycle transport timed out before producing a bounded result.") from exc
    if result.returncode != 0:
        raise RuntimeError("Remote lifecycle invocation failed.")
    return _parse_remote_output(result.stdout)


def invoke(body):
    if not isinstance(body, dict):
        raise ValueError("Lifecycle target requires a request body.")
    action = str(body.get("action") or "")
    if _platform_supported():
        if action.startswith("clone_") or action.startswith("retirement_"):
            resource = _load_resource_module()
            if action == "capabilities":
                return resource.describe_capabilities()
            if action == "clone_apply":
                return resource.apply_clone(body["native_candidate"], actor=body["actor"], intent_id=body["intent_id"])
            if action == "retirement_capture":
                return resource.capture_job_config(
                    body["job_name"],
                    actor=body.get("actor"),
                    intent_id=body.get("intent_id"),
                    review_digest=body.get("review_digest"),
                )
            if action == "retirement_delete":
                return resource.delete_job_config(
                    body["job_name"],
                    expected_path=body["expected_path"],
                    expected_digest=body["expected_digest"],
                    actor=body.get("actor"),
                    intent_id=body.get("intent_id"),
                    review_digest=body.get("review_digest"),
                )
            if action == "retirement_read":
                return resource.read_job_config(body["job_name"])
            if action == "retirement_restore":
                return resource.restore_job_config(
                    body["beforeimage"],
                    actor=body.get("actor"),
                    intent_id=body.get("intent_id"),
                    review_digest=body.get("review_digest"),
                    expected_destination_digest=body.get("expected_destination_digest"),
                )
        helper = _load_helper_module()
        helper.transport_ready()
        if action == "capabilities":
            return helper.capabilities()
        if action == "current":
            return helper.current(body["job_name"])
        if action == "review":
            return helper.review(body["lifecycle_action"], body["job_name"], body.get("definition"))
        if action in ("disable", "enable"):
            return helper.apply(body)
        if action == "status":
            return helper.status(body["request_id"])
    else:
        return _run_remote(body)
    raise ValueError("Unsupported lifecycle action.")


def _sha_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _local_review_hashes():
    hashes = {}
    for key, path in (
        ("helperHash", _helper_path()),
        ("resourceExecutorHash", _resource_executor_path()),
        ("policyHelperHash", _policy_helper_path()),
        ("onboardingContractHash", _onboarding_contract_path()),
    ):
        hashes[key] = _sha_bytes(path.read_bytes()) if path.exists() else None
    return hashes


def _capability_blocker(caps, reviewed_hashes):
    if caps.get("contractVersion") != CONTRACT_VERSION:
        return "Lifecycle native contract does not match the reviewed local build."
    for key, expected in reviewed_hashes.items():
        if expected and caps.get(key) != expected:
            return "Lifecycle native helper hashes do not match the reviewed local build."
    if not bool(caps.get("transportReady")):
        return "Lifecycle native transport is not ready."
    if not bool(caps.get("installedReady")):
        return "Lifecycle native helper is not fully installed."
    if not bool(caps.get("rootReady")):
        return "Lifecycle native helper is not running with root permissions."
    if not bool(caps.get("locksReady")):
        return "Lifecycle native locking prerequisites are not ready."
    if not bool(caps.get("securePathsReady", False)):
        return "Lifecycle native secure path prerequisites are not ready."
    if not bool(caps.get("prerequisitesComplete", False)):
        return "Lifecycle native prerequisites are incomplete."
    return None


def candidate_capabilities(values):
    enabled = values.get("BACKUPCENTER_LIFECYCLE_APPLY_ENABLED") == "1"
    reviewed_hashes = _local_review_hashes()
    try:
        caps = invoke({"action": "capabilities"})
        blocker = _capability_blocker(caps, reviewed_hashes)
    except Exception as exc:
        caps = {}
        blocker = "Lifecycle native capability probe failed."
    installed = bool(caps.get("installedReady"))
    reviewed_ready = blocker is None
    if not enabled and blocker is None:
        blocker = "Live lifecycle application is disabled."
    return {
        "candidateReady": True,
        "installedReady": installed,
        "reviewedReady": reviewed_ready,
        "applyEnabled": bool(enabled and reviewed_ready),
        "liveApplyBlocker": None if enabled and reviewed_ready else blocker or "Live lifecycle application is disabled.",
        "helperPath": str(_helper_path()),
        "resourceExecutorPath": str(_resource_executor_path()),
        "policyHelperPath": str(_policy_helper_path()),
        "onboardingContractPath": str(_onboarding_contract_path()),
        "remoteHelperPath": REMOTE_LIFECYCLE_HELPER,
        "remoteResourceExecutorPath": REMOTE_RESOURCE_EXECUTOR,
        "contractVersion": caps.get("contractVersion", CONTRACT_VERSION),
        "helperHash": caps.get("helperHash"),
        "resourceExecutorHash": caps.get("resourceExecutorHash"),
        "policyHelperHash": caps.get("policyHelperHash"),
        "onboardingContractHash": caps.get("onboardingContractHash"),
        "rootReady": bool(caps.get("rootReady")),
        "locksReady": bool(caps.get("locksReady")),
        "securePathsReady": bool(caps.get("securePathsReady")),
        "transportReady": bool(caps.get("transportReady")),
        "prerequisitesComplete": bool(caps.get("prerequisitesComplete")),
    }
