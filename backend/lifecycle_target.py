"""Lifecycle helper target adapter."""
from __future__ import annotations

import importlib
import os
from pathlib import Path


def _helper_path():
    return Path(__file__).resolve().parents[1] / "integration" / "apply_job_lifecycle.py"


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


def invoke(body):
    if not isinstance(body, dict):
        raise ValueError("Lifecycle target requires a request body.")
    helper = _load_helper_module()
    helper.transport_ready()
    action = body.get("action")
    if action == "current":
        return helper.current(body["job_name"])
    if action == "review":
        return helper.review(body["lifecycle_action"], body["job_name"], body.get("definition"))
    if action in ("disable", "enable"):
        return helper.apply(body)
    if action == "status":
        return helper.status(body["request_id"])
    raise ValueError("Unsupported lifecycle action.")


def candidate_capabilities(values):
    enabled = values.get("BACKUPCENTER_LIFECYCLE_APPLY_ENABLED") == "1"
    blocker = None
    installed = False
    try:
        helper = _load_helper_module()
        helper.transport_ready()
        installed = True
    except Exception as exc:
        blocker = str(exc)
    if not enabled and blocker is None:
        blocker = "Live lifecycle application is disabled."
    return {
        "candidateReady": True,
        "installedReady": installed,
        "applyEnabled": bool(enabled and installed),
        "liveApplyBlocker": None if enabled and installed else blocker or "Live lifecycle application is disabled.",
        "helperPath": str(_helper_path()),
    }
