"""Validate candidate schedules with native Director -t; never install or reload.

Run only on the existing Linux server. Candidate configuration (including local
resource secrets) stays in a private server-side temporary directory owned by
bareos. No configuration content or daemon transcript is printed/exported.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if os.name != "posix" or os.geteuid() != 0:
        print(json.dumps({"status": "unsupported", "reason": "Linux root validation only"}))
        return 2
    import pwd
    os.umask(0o077)
    staged = Path(__file__).resolve().parent
    contract = load("active_policy_contract", staged.parent / "backend/active_policy.py")
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    def forbidden(*args, **kwargs):
        raise RuntimeError("Console transport is forbidden in candidate validation")
    sys.modules["direct_vm_restore"] = types.SimpleNamespace(console=forbidden, require=require)
    helper = load("candidate_policy_helper", staged / "apply_backup_policy.py")
    base = Path("/etc/bareos/bareos-dir.d")
    files = sorted(base.glob("*/*.conf"))
    require(files, "Configuration resources not found")
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    raw = {path: path.read_text() for path in files}
    target = base / "job/PNET.conf"
    source = base / "job/MTIMRWKF01.conf"
    require(target in raw and source in raw, "Scoped fixture jobs unavailable")
    account = pwd.getpwnam("bareos")
    root = Path(tempfile.mkdtemp(prefix="backupcenter-director-check-"))
    os.chown(root, account.pw_uid, account.pw_gid)
    results = []
    calendars = {
        "daily_interval": contract.ScheduleCalendar(interval_hours=1),
        "monthly_ordinal": contract.ScheduleCalendar(mode="monthly_ordinal", full_mode="ordinal", ordinal_week=4, ordinal_weekday=6),
        "weekly": contract.ScheduleCalendar(mode="weekly", weekdays=[1, 3, 5], full_mode="weekly", full_weekday=5),
    }
    for label in [*calendars, "after_job"]:
        changed = dict(raw)
        job = changed[target]
        for key, value in {"Reschedule On Error": "yes", "Reschedule Times": "2", "Reschedule Interval": "1800", "Rerun Failed Levels": "yes"}.items():
            job = helper.set_directive(job, key, value)
        extra = ""
        if label == "after_job":
            job = helper.set_directive(job, "Schedule", None)
            definition = contract.ActivePolicy(jobs=["VMware-PNET"], time_wita="22:15", retention_days=30, maximum_volumes=8, trigger_mode="after_job", after_job={"source_job": "VMware-MTIMRWKF01", "on_failure": "run_anyway", "level": "incremental"}, window_end_wita="23:30").model_dump()
            changed[source] = helper.add_dependency_block(changed[source], "VMware-PNET", definition)
        else:
            name = "BC-Native-Candidate"
            job = helper.set_directive(job, "Schedule", name)
            extra = contract.calendar_schedule(name, "22:15", True, calendars[label], "23:30" if label == "daily_interval" else None)
        changed[target] = job
        config = root / (label + ".conf")
        config.write_text("\n".join(changed[path] for path in files) + "\n" + extra)
        os.chown(config, account.pw_uid, account.pw_gid)
        result = subprocess.run(["runuser", "-u", "bareos", "--", "/opt/bareos/25.1.1/sbin/bareos-dir", "-t", "-c", str(config)], cwd="/var/lib/bareos", text=True, capture_output=True, timeout=45)
        # Transcript may contain secret-bearing source lines; retain locally only.
        transcript = root / (label + ".log")
        transcript.write_text(result.stdout + result.stderr)
        results.append({"case": label, "exit": result.returncode, "passed": result.returncode == 0})
    unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in before.items())
    print(json.dumps({"status": "passed" if unchanged and all(row["passed"] for row in results) else "failed", "checks": results, "production_config_unchanged": unchanged, "private_server_evidence": str(root)}))
    return 0 if unchanged and all(row["passed"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
