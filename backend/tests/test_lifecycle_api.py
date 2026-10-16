import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend import app as module
from backend.lifecycle_target import candidate_capabilities
from backend.operations import dispatch
from integration import apply_job_lifecycle as helper


HEADERS = {"Origin": "http://127.0.0.1:3000", "X-Backup-Center-Action": "confirmed"}


class Store:
    configured = True

    def __init__(self):
        self.rows = {}
        self.revisions = {}
        self.last_revision = None

    def assignment_detail(self, job_name):
        return {"inventory_vm_id": "managed.pnet", "instance_uuid": "11111111-1111-1111-1111-111111111111", "storage_name": "repo-primary"}

    def lifecycle_operations(self, job_name):
        return [dict(row) for row in self.rows.values() if row["parameters"].get("jobName") == job_name and row["state"] in ("Prepared", "Dispatching", "Accepted", "Running", "Unknown")]

    def latest_lifecycle_revision(self, job_name):
        return self.last_revision

    def actor_allowed(self, username, kind="provision"):
        return True

    def operation_key(self, key):
        return next((row for row in self.rows.values() if str(row["idempotency_key"]) == str(key)), None)

    def prepare_lifecycle(self, key, actor, plan):
        existing = self.operation_key(key)
        if existing:
            if existing["actor"] != actor:
                raise ValueError("Request key belongs to another lifecycle intent.")
            payload = self.revisions[existing["target"]]["payload"]
            if payload["action"] != plan["action"] or payload["reviewDigest"] != plan["reviewDigest"] or payload["proofRevision"] != plan["proofRevision"] or payload.get("definition") != plan.get("definition"):
                raise ValueError("Request key belongs to another lifecycle intent.")
            return dict(existing)
        if any(row["parameters"].get("jobName") == plan["jobName"] and row["state"] in ("Prepared", "Dispatching", "Accepted", "Running", "Unknown") for row in self.rows.values()):
            raise ValueError("An unresolved lifecycle operation already exists for this job.")
        revision_id = str(uuid4())
        self.revisions[revision_id] = {"payload": dict(plan), "state": "Prepared"}
        row = {
            "id": str(uuid4()),
            "idempotency_key": str(key),
            "kind": "provision",
            "target": revision_id,
            "state": "Prepared",
            "parameters": {"jobName": plan["jobName"], "summary": plan["summary"]},
            "actor": actor,
        }
        self.rows[row["id"]] = row
        return dict(row)

    def provision_revision(self, revision_id):
        value = self.revisions.get(str(revision_id))
        return {"payload": dict(value["payload"]), "state": value["state"]} if value else None

    def finish_lifecycle(self, revision_id, actor, state, details):
        self.revisions[str(revision_id)]["state"] = state
        self.revisions[str(revision_id)]["payload"].update(details)
        self.last_revision = {"state": state, "payload": dict(self.revisions[str(revision_id)]["payload"])}
        return self.revisions[str(revision_id)]

    def transition(self, oid, expected, state, job_id=None, message="", session_status=None):
        row = self.rows[oid]
        if row["state"] not in expected:
            return None
        row["state"] = state
        row["parameters"] = {**row["parameters"], "message": message}
        return dict(row)


class Gateway:
    def __init__(self):
        self.store = Store()
        self.values = {"BACKUPCENTER_LIFECYCLE_APPLY_ENABLED": "1"}
        self.operation_jobs = {"VMware-PNET"}


class FakeLock:
    LOCK_EX = 1
    LOCK_NB = 2

    @staticmethod
    def flock(fd, flags):
        return None


class FakePolicy:
    def __init__(self, base: Path, trigger_name: str = "backupcenter-after-job.py"):
        self.BASE = base
        self.NAMES = {"PNET", "SRC"}
        self.TRIGGER = base.parent / trigger_name
        self.TRIGGER.write_text("print('trigger')\n")
        self.__file__ = str(base.parent / "fake_apply_backup_policy.py")
        self.syntax_error = None
        self.console_error = None

    def paths(self, vm):
        return self.BASE / "job" / f"{vm}.conf", self.BASE / "pool" / f"{vm}.conf", self.BASE / "schedule" / f"BC-Policy-{vm}.conf"

    def policy_marker(self, text):
        match = re.search(r"^# BackupCenter policy: (.+)$", text, re.M)
        return json.loads(match.group(1)) if match else None

    def set_directive(self, text, name, value):
        pattern = rf"(?m)^\s*{re.escape(name)}\s*=.*\n?"
        line = "" if value is None else f" {name} = {value}\n"
        if re.search(pattern, text):
            return re.sub(pattern, line, text)
        if value is None:
            return text
        return re.sub(r"(?m)^}\s*$", line + "}", text, count=1)

    def set_marker(self, text, payload):
        pattern = r"(?m)^# BackupCenter policy: .*\n?"
        line = "# BackupCenter policy: " + json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        if re.search(pattern, text):
            return re.sub(pattern, line, text)
        return re.sub(r"(?m)^}\s*$", line + "}", text, count=1)

    def drop_dependency_block(self, text, target):
        pattern = rf"(?ms)^# BackupCenter dependency trigger begin: {re.escape(target)}\n.*?^# BackupCenter dependency trigger end: {re.escape(target)}\n?"
        return re.sub(pattern, "", text)

    def add_dependency_block(self, text, target, definition):
        block = (
            f"# BackupCenter dependency trigger begin: {target}\n"
            f" Run After Job = \"python {self.TRIGGER} --source {definition['after_job']['source_job']} --target {target}\"\n"
            f"# BackupCenter dependency trigger end: {target}\n"
        )
        return re.sub(r"(?m)^}\s*$", lambda _: block + "}", self.drop_dependency_block(text, target), count=1)

    def calendar_schedule(self, name, time_wita, automatic, calendar=None, window_end_wita=None):
        body = f"Schedule {{\n Name = {name}\n Run = Full at {time_wita}\n"
        if not automatic:
            body += " Enabled = no\n"
        return body + "}\n"

    def verify_retry_directives(self, text, definition):
        expected = {
            "Reschedule On Error": "yes" if definition["retry_count"] else "no",
            "Reschedule Times": str(definition["retry_count"]) if definition["retry_count"] else None,
            "Reschedule Interval": str(definition["retry_interval_minutes"] * 60) if definition["retry_count"] else None,
            "Rerun Failed Levels": "yes" if definition["retry_count"] else None,
        }
        for key, wanted in expected.items():
            found = re.findall(rf"^\s*{re.escape(key)}\s*=\s*([^\n]+)", text, re.M)
            if wanted == "no" and not found:
                continue
            if found != ([] if wanted is None else [wanted]):
                raise ValueError("Retry directives differ from reviewed policy; inspect configuration before editing.")

    def verify_hooks(self, jobs, target, definition):
        source = (definition.get("after_job") or {}).get("source_job")
        block = f"# BackupCenter dependency trigger begin: {target}"
        present = sorted(job for job, text in jobs.items() if block in text)
        if definition["trigger_mode"] == "after_job":
            if present != [source[7:]]:
                raise ValueError("Dependency hook block does not match the reviewed hook.")
        elif present:
            raise ValueError("Dependency hook markers must be absent.")

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def syntax(self):
        if self.syntax_error:
            raise self.syntax_error

    def console(self, command):
        if self.console_error:
            raise self.console_error
        return {"ok": True}

    def active(self):
        return None


def _definition(trigger_mode="calendar"):
    base = {
        "jobs": ["VMware-PNET"],
        "time_wita": "21:30",
        "retention_days": 30,
        "maximum_volumes": 12,
        "automatic": True,
        "retry_count": 2,
        "retry_interval_minutes": 30,
    }
    if trigger_mode == "calendar":
        return {**base, "trigger_mode": "calendar", "calendar": None, "window_end_wita": None}
    return {
        **base,
        "trigger_mode": "after_job",
        "calendar": None,
        "window_end_wita": None,
        "after_job": {"source_job": "VMware-SRC", "level": "Incremental", "on_failure": "skip"},
    }


def _job_text(policy: FakePolicy, vm: str, definition: dict):
    job_name = f"VMware-{vm}"
    text = (
        "Job {\n"
        f" Name = {job_name}\n"
        f" FileSet = {job_name}\n"
        f" Pool = {vm}\n"
        f" Reschedule On Error = {'yes' if definition['retry_count'] else 'no'}\n"
        + (f" Reschedule Times = {definition['retry_count']}\n" if definition["retry_count"] else "")
        + (f" Reschedule Interval = {definition['retry_interval_minutes'] * 60}\n" if definition["retry_count"] else "")
        + (" Rerun Failed Levels = yes\n" if definition["retry_count"] else "")
    )
    if definition["trigger_mode"] == "calendar":
        text += f" Schedule = BC-Policy-{vm}\n"
    text += "}\n"
    return policy.set_marker(text, definition)


def _prepare_policy(tmp_path: Path, trigger_mode="calendar"):
    base = tmp_path / "bareos-dir.d"
    for name in ("job", "pool", "schedule"):
        (base / name).mkdir(parents=True, exist_ok=True)
    policy = FakePolicy(base)
    definition = _definition(trigger_mode)
    pnet_job, pnet_pool, pnet_schedule = policy.paths("PNET")
    pnet_job.write_text(_job_text(policy, "PNET", definition))
    pnet_pool.write_text("Pool {\n Name = PNET\n Volume Retention = 30 days\n Maximum Volumes = 12\n AutoPrune = no\n Recycle = yes\n}\n")
    if trigger_mode == "calendar":
        pnet_schedule.write_text(policy.calendar_schedule("BC-Policy-PNET", "21:30", True, None, None))
    src_definition = _definition("calendar")
    src_job, src_pool, src_schedule = policy.paths("SRC")
    src_job.write_text(_job_text(policy, "SRC", src_definition))
    src_pool.write_text("Pool {\n Name = SRC\n Volume Retention = 30 days\n Maximum Volumes = 12\n AutoPrune = no\n Recycle = yes\n}\n")
    src_schedule.write_text(policy.calendar_schedule("BC-Policy-SRC", "22:00", True, None, None))
    if trigger_mode == "after_job":
        src_job.write_text(policy.add_dependency_block(src_job.read_text(), "VMware-PNET", definition))
    return policy, definition


@pytest.fixture
def lifecycle_env(tmp_path, monkeypatch):
    policy, definition = _prepare_policy(tmp_path, "calendar")
    gateway = Gateway()
    monkeypatch.setattr("backend.auth.session_user", lambda _: {"username": "admin", "role": "Admin"})
    monkeypatch.setattr(module, "gateway", lambda: gateway)
    monkeypatch.setattr("backend.lifecycle_target._platform_supported", lambda: True)
    monkeypatch.setattr("backend.lifecycle_target._load_helper_module", lambda: helper)
    monkeypatch.setattr(helper, "_load_policy_module", lambda: policy)
    monkeypatch.setattr(helper, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(helper, "_fsync_dir", lambda path: None)
    monkeypatch.setattr(helper, "ROOT", tmp_path / "receipts")
    monkeypatch.setattr(helper, "LOCK", tmp_path / "lock")
    with TestClient(module.app) as client:
        yield client, gateway, policy, definition, tmp_path


def test_disable_preview_preserves_old_shape_and_blocks_without_helper_transport(monkeypatch):
    monkeypatch.setattr("backend.lifecycle_target._platform_supported", lambda: False)
    caps = candidate_capabilities({"BACKUPCENTER_LIFECYCLE_APPLY_ENABLED": "1"})
    assert caps["applyEnabled"] is False
    assert "POSIX" in caps["liveApplyBlocker"]


def test_disable_review_exposes_digest_alias(lifecycle_env):
    client, _, _, _, _ = lifecycle_env
    response = client.post("/api/jobs/disable/preview", headers=HEADERS, json={"job_name": "VMware-PNET"})
    assert response.status_code == 200
    body = response.json()
    assert body["digest"] == body["reviewDigest"]


def test_api_worker_helper_disable_then_enable_round_trip(lifecycle_env):
    client, gateway, policy, definition, _ = lifecycle_env
    disable_review = client.post("/api/jobs/lifecycle/disable/review", headers=HEADERS, json={"jobName": "VMware-PNET"}).json()
    assert disable_review["readiness"] == "candidate_ready"
    disable_body = {
        "jobName": "VMware-PNET",
        "idempotencyKey": str(uuid4()),
        "reviewDigest": disable_review["reviewDigest"],
        "proofRevision": disable_review["proofRevision"],
        "confirmed": True,
    }
    prepared = client.post("/api/jobs/lifecycle/disable", headers=HEADERS, json=disable_body)
    assert prepared.status_code == 202
    asyncio.run(dispatch(gateway, prepared.json()))
    job_text = policy.paths("PNET")[0].read_text()
    assert " Schedule =" not in job_text
    assert gateway.store.last_revision["state"] == "Validated"
    enable_review = client.post("/api/jobs/lifecycle/enable/review", headers=HEADERS, json={"jobName": "VMware-PNET"}).json()
    assert enable_review["readiness"] == "candidate_ready"
    enable_body = {
        "jobName": "VMware-PNET",
        "idempotencyKey": str(uuid4()),
        "reviewDigest": enable_review["reviewDigest"],
        "proofRevision": enable_review["proofRevision"],
        "confirmed": True,
    }
    prepared_enable = client.post("/api/jobs/lifecycle/enable", headers=HEADERS, json=enable_body)
    assert prepared_enable.status_code == 202
    asyncio.run(dispatch(gateway, prepared_enable.json()))
    assert "Schedule = BC-Policy-PNET" in policy.paths("PNET")[0].read_text()
    assert policy.paths("PNET")[2].exists()


def test_real_helper_after_job_retry_round_trip(tmp_path, monkeypatch):
    policy, definition = _prepare_policy(tmp_path, "after_job")
    monkeypatch.setattr(helper, "_load_policy_module", lambda: policy)
    monkeypatch.setattr(helper, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(helper, "_fsync_dir", lambda path: None)
    monkeypatch.setattr(helper, "ROOT", tmp_path / "receipts")
    monkeypatch.setattr(helper, "LOCK", tmp_path / "lock")
    reviewed_disable = helper.review("disable", "VMware-PNET")
    disabled = helper.apply(
        {
            "action": "disable",
            "job_name": "VMware-PNET",
            "request_id": str(uuid4()),
            "digest": reviewed_disable["reviewDigest"],
            "proof_revision": reviewed_disable["proofRevision"],
            "definition": reviewed_disable["definition"],
            "actor": "admin",
        }
    )
    assert disabled["state"] == "Applied"
    assert "# BackupCenter dependency trigger begin: VMware-PNET" not in policy.paths("SRC")[0].read_text()
    assert "Reschedule On Error = no" in policy.paths("PNET")[0].read_text()
    reviewed_enable = helper.review("enable", "VMware-PNET", definition)
    enabled = helper.apply(
        {
            "action": "enable",
            "job_name": "VMware-PNET",
            "request_id": str(uuid4()),
            "digest": reviewed_enable["reviewDigest"],
            "proof_revision": reviewed_enable["proofRevision"],
            "definition": definition,
            "actor": "admin",
        }
    )
    assert enabled["state"] == "Applied"
    assert "# BackupCenter dependency trigger begin: VMware-PNET" in policy.paths("SRC")[0].read_text()
    assert "Reschedule Times = 2" in policy.paths("PNET")[0].read_text()


def test_helper_rollback_and_idempotency_are_durable(tmp_path, monkeypatch):
    policy, _ = _prepare_policy(tmp_path, "calendar")
    monkeypatch.setattr(helper, "_load_policy_module", lambda: policy)
    monkeypatch.setattr(helper, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(helper, "_fsync_dir", lambda path: None)
    monkeypatch.setattr(helper, "ROOT", tmp_path / "receipts")
    monkeypatch.setattr(helper, "LOCK", tmp_path / "lock")
    reviewed = helper.review("disable", "VMware-PNET")
    request_id = str(uuid4())
    calls = {"count": 0}
    def fail_once():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("syntax failed")
    monkeypatch.setattr(policy, "syntax", fail_once)
    failed = helper.apply(
        {
            "action": "disable",
            "job_name": "VMware-PNET",
            "request_id": request_id,
            "digest": reviewed["reviewDigest"],
            "proof_revision": reviewed["proofRevision"],
            "definition": reviewed["definition"],
            "actor": "admin",
        }
    )
    assert failed["state"] == "Failed"
    assert "Schedule = BC-Policy-PNET" in policy.paths("PNET")[0].read_text()
    before_path = Path(failed["beforeImagesPath"])
    assert before_path.exists()
    replay = helper.apply(
        {
            "action": "disable",
            "job_name": "VMware-PNET",
            "request_id": request_id,
            "digest": reviewed["reviewDigest"],
            "proof_revision": reviewed["proofRevision"],
            "definition": reviewed["definition"],
            "actor": "admin",
        }
    )
    assert replay["state"] == "Failed"


def test_missing_dependency_is_fail_closed(tmp_path, monkeypatch):
    _prepare_policy(tmp_path, "calendar")
    monkeypatch.setattr("backend.lifecycle_target._platform_supported", lambda: True)
    monkeypatch.setattr("backend.lifecycle_target._load_helper_module", lambda: helper)
    monkeypatch.setattr(helper, "_load_policy_module", lambda: (_ for _ in ()).throw(RuntimeError("Lifecycle helper dependency unavailable: fake.")))
    monkeypatch.setattr(helper, "_load_lock_module", lambda: FakeLock)
    monkeypatch.setattr(helper, "_fsync_dir", lambda path: None)
    caps = candidate_capabilities({"BACKUPCENTER_LIFECYCLE_APPLY_ENABLED": "1"})
    assert caps["applyEnabled"] is False
    assert "dependency unavailable" in caps["liveApplyBlocker"]
