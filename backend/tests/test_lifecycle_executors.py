import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend import lifecycle_executors, lifecycle_target
from integration import apply_job_lifecycle as helper
from integration import lifecycle_resource_executor as native_exec
from integration.onboarding_contract import build as build_onboarding_bundle


class FakeLock:
    LOCK_EX = 1
    LOCK_NB = 2

    @staticmethod
    def flock(fd, flags):
        return None


def _manualized_candidate(vm_uuid: str, label: str) -> dict:
    bundle = build_onboarding_bundle(vm_uuid, label)
    files = dict(bundle["files"])
    job_key = f"bareos-dir.d/job/{label}.conf"
    rows = []
    for raw in files[job_key].splitlines():
        if raw.strip().startswith("Schedule ="):
            continue
        if raw.strip() == "Enabled = yes":
            rows.append(" Enabled = no")
            continue
        rows.append(raw)
    files[job_key] = "\n".join(rows) + "\n"
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
        "resourceDigest": native_exec._json_digest(resource_plan),
        "candidateDigest": native_exec._json_digest(
            {
                "automaticSchedule": False,
                "enabled": False,
                "historyCopied": False,
                "secretsCopied": False,
                "resourcePlan": resource_plan,
            }
        ),
    }


def _bind_candidate(candidate: dict, *, actor: str, repository_id: str = "repo-1") -> dict:
    plan = candidate["resourcePlan"]
    binding = {
        "protocol": native_exec.CLONE_BINDING_PROTOCOL,
        "contractVersion": native_exec.CONTRACT_VERSION,
        "complete": True,
        "actor": actor,
        "targetJobName": plan["job"],
        "targetVmUuid": re.search(r":uuid=([0-9a-fA-F-]{36})", plan["files"][f"bareos-dir.d/fileset/{plan['pool']}.conf"]).group(1),
        "resourceLabel": plan["pool"],
        "repositoryId": repository_id,
        "candidateDigest": candidate["candidateDigest"],
        "resourceDigest": candidate["resourceDigest"],
        "reviewDigest": "a" * 64,
        "proofRevision": 7,
        "proofCoverage": ["registry", "collector", "store", "inventory"],
    }
    binding["bindingDigest"] = native_exec._binding_digest(
        binding,
        ("protocol", "contractVersion", "complete", "actor", "targetJobName", "targetVmUuid", "resourceLabel", "repositoryId", "candidateDigest", "resourceDigest", "reviewDigest", "proofRevision", "proofCoverage"),
    )
    return {**candidate, "binding": binding}


@pytest.fixture
def native_env(tmp_path, monkeypatch):
    root = tmp_path / "etc" / "bareos"
    dir_base = root / "bareos-dir.d"
    sd_base = root / "bareos-sd.d"
    for path in (
        dir_base / "storage",
        dir_base / "pool",
        dir_base / "fileset",
        dir_base / "job",
        sd_base / "device",
        tmp_path / "bin",
        tmp_path / "receipts",
        tmp_path / "run" / "lock",
        tmp_path / "mnt" / "bareos-smb",
    ):
        path.mkdir(parents=True, exist_ok=True)
    for name in ("bareos-dir", "bareos-sd", "bconsole"):
        (tmp_path / "bin" / name).write_text("#!/bin/sh\nexit 0\n")
    (dir_base / "storage" / "VeeamSMB.conf").write_text('Storage {\n Name = VeeamSMB\n Password = "secret-value"\n}\n')
    monkeypatch.setattr(native_exec, "ROOT", root)
    monkeypatch.setattr(native_exec, "DIR_BASE", dir_base)
    monkeypatch.setattr(native_exec, "SD_BASE", sd_base)
    monkeypatch.setattr(native_exec, "BIN", tmp_path / "bin")
    monkeypatch.setattr(native_exec, "RECEIPTS", tmp_path / "receipts")
    monkeypatch.setattr(native_exec, "LIFECYCLE_LOCK", tmp_path / "run" / "lock" / "native.lock")
    monkeypatch.setattr(native_exec, "STORAGE_SECRET_PATH", dir_base / "storage" / "VeeamSMB.conf")
    monkeypatch.setattr(native_exec, "SMB_ROOT", tmp_path / "mnt" / "bareos-smb")
    monkeypatch.setattr(native_exec, "HELPER_RECEIPTS", tmp_path / "helper-receipts")
    monkeypatch.setattr(native_exec, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(native_exec, "_safe_chown", lambda path, user, group: None)
    monkeypatch.setattr(native_exec, "_fsync_dir", lambda path: None)
    monkeypatch.setattr(native_exec.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(native_exec, "_secure_owned_path", lambda path, allow_missing=False: None)
    def fake_cmd(args, *, input=None, timeout=60):
        text = input or ""
        if "show job=" in text:
            name = re.search(r"show job=([^\n]+)", text).group(1).strip()
            job_file = native_exec.DIR_BASE / "job" / f"{name[7:]}.conf"
            stdout = f'Name = "{name}"\n' if job_file.exists() else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if "show storage=" in text:
            name = re.search(r"show storage=([^\n]+)", text).group(1).strip()
            storage_file = native_exec.DIR_BASE / "storage" / f"{name}.conf"
            stdout = f'Name = "{name}"\n' if storage_file.exists() else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(native_exec, "_cmd", fake_cmd)
    return tmp_path


def test_remote_command_hides_raw_injection():
    command = lifecycle_target._remote_command(
        lifecycle_target.REMOTE_RESOURCE_EXECUTOR,
        {"action": "clone_apply", "job_name": "VMware-PNET;rm -rf /", "actor": "admin"},
    )
    assert "rm -rf" not in command
    assert lifecycle_target.REMOTE_RESOURCE_EXECUTOR in command
    assert "base64 -d" in command
    assert lifecycle_target.REMOTE_VMWARE_PYTHONPATH in command


def test_candidate_capabilities_remain_blocked_without_real_transport(monkeypatch):
    monkeypatch.setattr(lifecycle_target, "_platform_supported", lambda: False)
    monkeypatch.setattr(
        lifecycle_target,
        "_run_remote",
        lambda body: {
            "contractVersion": "x",
            "installedReady": False,
            "transportReady": True,
            "rootReady": False,
            "locksReady": False,
            "securePathsReady": False,
            "prerequisitesComplete": False,
            "helperHash": None,
            "resourceExecutorHash": None,
            "policyHelperHash": None,
            "onboardingContractHash": None,
            "blocker": "Remote helper is not installed.",
        },
    )
    caps = lifecycle_target.candidate_capabilities({"BACKUPCENTER_LIFECYCLE_APPLY_ENABLED": "1"})
    assert caps["applyEnabled"] is False
    assert caps["installedReady"] is False
    assert caps["liveApplyBlocker"] == "Lifecycle native contract does not match the reviewed local build."


def test_helper_review_blocks_runtime_pending(tmp_path, monkeypatch):
    base = tmp_path / "bareos-dir.d"
    for name in ("job", "pool", "schedule"):
        (base / name).mkdir(parents=True, exist_ok=True)
    trigger = tmp_path / "backupcenter-after-job.py"
    trigger.write_text("print('ok')\n")
    job = base / "job" / "PNET.conf"
    pool = base / "pool" / "PNET.conf"
    schedule = base / "schedule" / "BC-Policy-PNET.conf"
    definition = {"jobs": ["VMware-PNET"], "time_wita": "21:30", "retention_days": 30, "maximum_volumes": 12, "automatic": True, "trigger_mode": "calendar", "calendar": None, "window_end_wita": None, "retry_count": 2, "retry_interval_minutes": 30}
    policy = SimpleNamespace(
        BASE=base,
        NAMES={"PNET"},
        TRIGGER=trigger,
        __file__=str(tmp_path / "apply_backup_policy.py"),
        paths=lambda vm: (base / "job" / f"{vm}.conf", base / "pool" / f"{vm}.conf", base / "schedule" / f"BC-Policy-{vm}.conf"),
        policy_marker=lambda text: json.loads(re.search(r"^# BackupCenter policy: (.+)$", text, re.M).group(1)),
        verify_retry_directives=lambda text, definition: None,
        verify_hooks=lambda jobs, target, definition: None,
        active=lambda: None,
    )
    def set_directive(text, name, value):
        pattern = rf"(?m)^\s*{re.escape(name)}\s*=.*\n?"
        line = "" if value is None else f" {name} = {value}\n"
        if re.search(pattern, text):
            return re.sub(pattern, line, text)
        return text
    policy.set_directive = set_directive
    policy.set_marker = lambda text, payload: re.sub(r"(?m)^}\s*$", '# BackupCenter policy: ' + json.dumps(payload, sort_keys=True, separators=(",", ":")) + '\n}', text, count=1)
    policy.drop_dependency_block = lambda text, target: text
    policy.add_dependency_block = lambda text, target, definition: text
    policy.write = lambda path, text: Path(path).write_text(text)
    policy.syntax = lambda: None
    policy.console = lambda command: {"ok": True}
    job.write_text(policy.set_marker("Job {\n Name = VMware-PNET\n FileSet = VMware-PNET\n Pool = PNET\n Schedule = BC-Policy-PNET\n Reschedule On Error = yes\n Reschedule Times = 2\n Reschedule Interval = 1800\n Rerun Failed Levels = yes\n}\n", definition))
    pool.write_text("Pool {}\n")
    schedule.write_text("Schedule {}\n")
    monkeypatch.setattr(helper, "_load_policy_module", lambda: policy)
    monkeypatch.setattr(helper, "_load_resource_module", lambda: SimpleNamespace(__file__=str(tmp_path / "lifecycle_resource_executor.py"), describe_capabilities=lambda: {"installedReady": True}))
    monkeypatch.setattr(helper, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(helper, "ROOT", tmp_path / "receipts")
    monkeypatch.setattr(helper, "LOCK", tmp_path / "lock")
    monkeypatch.setenv("BACKUPCENTER_AFTER_JOB_STATE", str(tmp_path / "runtime"))
    runtime = tmp_path / "runtime" / "receipts"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "pending.json").write_text(json.dumps({"target": "VMware-PNET", "state": "Deferred"}))
    with pytest.raises(ValueError, match="After-job runtime receipt"):
        helper.review("disable", "VMware-PNET")


def test_native_capabilities_report_real_prereqs(native_env):
    caps = native_exec.describe_capabilities()
    assert caps["installedReady"] is True
    assert caps["rootReady"] is True
    assert caps["securePathsReady"] is True
    assert caps["prerequisitesComplete"] is True
    assert caps["helperHash"] is None or len(caps["helperHash"]) == 64
    assert len(caps["resourceExecutorHash"]) == 64
    assert len(caps["onboardingContractHash"]) == 64


def test_clone_apply_replay_and_wrong_actor_and_secret_resolution(native_env):
    candidate = _bind_candidate(_manualized_candidate("11111111-1111-1111-1111-111111111111", "CLONE"), actor="admin")
    intent = str(uuid4())
    first = native_exec.apply_clone(candidate, actor="admin", intent_id=intent)
    assert first["state"] == "applied"
    storage_text = (native_exec.DIR_BASE / "storage" / "CLONE.conf").read_text()
    assert "<existing-storage-secret>" not in storage_text
    same = native_exec.apply_clone(candidate, actor="admin", intent_id=intent)
    replay = native_exec.apply_clone(candidate, actor="admin", intent_id=intent)
    assert replay["nativeReceipt"] == same["nativeReceipt"]
    with pytest.raises(ValueError, match="another clone intent"):
        native_exec.apply_clone(candidate, actor="other", intent_id=intent)


def test_clone_apply_blocks_existing_shared_target(native_env):
    candidate = _bind_candidate(_manualized_candidate("11111111-1111-1111-1111-111111111111", "SHARED"), actor="admin")
    target = native_exec.DIR_BASE / "job" / "SHARED.conf"
    target.write_text("existing\n")
    with pytest.raises(ValueError, match="already exist"):
        native_exec.apply_clone(candidate, actor="admin", intent_id=str(uuid4()))


def test_clone_apply_unknown_when_reload_and_rollback_are_uncertain(native_env, monkeypatch):
    candidate = _bind_candidate(_manualized_candidate("11111111-1111-1111-1111-111111111111", "BROKEN"), actor="admin")
    monkeypatch.setattr(native_exec, "_syntax_and_reload", lambda: (_ for _ in ()).throw(RuntimeError("reload failed")))
    monkeypatch.setattr(native_exec, "_restore_before", lambda before: (_ for _ in ()).throw(RuntimeError("rollback failed")))
    result = native_exec.apply_clone(candidate, actor="admin", intent_id=str(uuid4()))
    assert result["state"] == "unknown"
    receipt = Path(result["nativeReceipt"])
    assert receipt.exists()
    assert json.loads(receipt.read_text())["state"] == "Unknown"


def test_retirement_capture_delete_restore_uses_opaque_beforeimage(native_env):
    job = native_exec.DIR_BASE / "job" / "RETIRE.conf"
    job.write_text("Job {\n Name = VMware-RETIRE\n}\n")
    review_digest = "b" * 64
    intent = str(uuid4())
    captured = native_exec.capture_job_config("VMware-RETIRE", actor="admin", intent_id=intent, review_digest=review_digest)
    assert "content" not in captured
    opaque = json.loads(Path(captured["opaqueRef"]).read_text())
    assert opaque["content"]
    deleted = native_exec.delete_job_config("VMware-RETIRE", expected_path=str(job), expected_digest=captured["digest"], actor="admin", intent_id=intent, review_digest=review_digest)
    assert deleted["deleted"] is True
    assert native_exec.read_job_config("VMware-RETIRE")["exists"] is False
    restored = native_exec.restore_job_config(captured, actor="admin", intent_id=intent, review_digest=review_digest)
    assert restored["restored"] is True
    assert native_exec.read_job_config("VMware-RETIRE")["exists"] is True


def test_retirement_delete_rejects_wrong_path(native_env):
    job = native_exec.DIR_BASE / "job" / "PATH.conf"
    job.write_text("Job {\n Name = VMware-PATH\n}\n")
    captured = native_exec.capture_job_config("VMware-PATH", actor="admin", intent_id=str(uuid4()), review_digest="c" * 64)
    with pytest.raises(ValueError, match="does not match"):
        native_exec.delete_job_config("VMware-PATH", expected_path=str(job) + ".other", expected_digest=captured["digest"], actor="admin", intent_id=captured["intentId"], review_digest=captured["reviewDigest"])


def test_clone_apply_blocks_hash_mismatch_before_writes(native_env):
    candidate = _bind_candidate(_manualized_candidate("11111111-1111-1111-1111-111111111111", "HASH"), actor="admin")
    candidate["binding"]["candidateDigest"] = "d" * 64
    with pytest.raises(ValueError, match="candidate digest drifted"):
        native_exec.apply_clone(candidate, actor="admin", intent_id=str(uuid4()))
    assert not (native_exec.DIR_BASE / "job" / "HASH.conf").exists()


def test_clone_apply_blocks_runtime_unknown_before_writes(native_env):
    candidate = _bind_candidate(_manualized_candidate("11111111-1111-1111-1111-111111111111", "RUNTIME"), actor="admin")
    receipts = native_exec._after_job_runtime_state_dir() / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "runtime.json").write_text(json.dumps({"target": "VMware-RUNTIME", "state": "Unknown"}))
    with pytest.raises(ValueError, match="unresolved lifecycle or runtime receipts"):
        native_exec.apply_clone(candidate, actor="admin", intent_id=str(uuid4()))
    assert not (native_exec.DIR_BASE / "job" / "RUNTIME.conf").exists()


def test_retirement_restore_rejects_untrusted_beforeimage_path(native_env):
    outside = native_env / "outside.json"
    outside.write_text(json.dumps({"opaqueRef": str(outside), "jobName": "VMware-BAD", "path": "x", "digest": "e" * 64, "actor": "admin", "intentId": str(uuid4()), "reviewDigest": "f" * 64, "content": ""}))
    with pytest.raises(ValueError, match="trusted receipt root|not trusted"):
        native_exec.restore_job_config({"opaqueRef": str(outside), "actor": "admin", "intentId": json.loads(outside.read_text())["intentId"], "reviewDigest": "f" * 64}, actor="admin", intent_id=json.loads(outside.read_text())["intentId"], review_digest="f" * 64)


def test_backend_executor_adapters_and_readiness(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle_target, "invoke", lambda body: calls.append(body) or {"ok": True})
    monkeypatch.setattr(lifecycle_target, "candidate_capabilities", lambda values: {"installedReady": True, "transportReady": True, "reviewedReady": True})
    clone = lifecycle_executors.RemoteCloneExecutor()
    retire = lifecycle_executors.RemoteRetirementConfigExecutor()
    assert clone.apply_clone({"candidateDigest": "x"}, actor="admin", intent_id="11111111-1111-1111-1111-111111111111") == {"ok": True}
    assert retire.capture_job_config("VMware-PNET", actor="admin", intent_id="11111111-1111-1111-1111-111111111111", review_digest="a" * 64) == {"ok": True}
    assert retire.delete_job_config("VMware-PNET", expected_path="/x", expected_digest="d", actor="admin", intent_id="11111111-1111-1111-1111-111111111111", review_digest="a" * 64) == {"ok": True}
    assert retire.read_job_config("VMware-PNET") == {"ok": True}
    assert retire.restore_job_config({"opaqueRef": "/x"}, actor="admin", intent_id="11111111-1111-1111-1111-111111111111", review_digest="a" * 64, expected_destination_digest="b" * 64) == {"ok": True}
    readiness = lifecycle_executors.extra_readiness(
        {},
        clone_collector=SimpleNamespace(collect_clone_review=lambda *args: None),
        retirement_collector=SimpleNamespace(collect_retirement_proof=lambda *args: None),
        store=SimpleNamespace(
            get_intent=lambda x: None,
            begin=lambda: None,
            load_retirement_operation=lambda x: None,
            create_retirement_operation=lambda x: None,
            save_retirement_record=lambda *args: None,
            finalize_retirement_operation=lambda *args: None,
            load_retirement_record=lambda *args: None,
        ),
    )
    assert readiness == {
        "installedReady": True,
        "transportReady": True,
        "collectorReady": True,
        "durableStoreReady": True,
        "executorReady": True,
    }
    assert [row["action"] for row in calls] == ["clone_apply", "retirement_capture", "retirement_delete", "retirement_read", "retirement_restore"]
