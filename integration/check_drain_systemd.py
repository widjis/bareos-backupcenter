"""Run fake-dispatch native harness through a unique transient systemd timer.
Never installs the production drain units or dispatches Bareos jobs.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4


def run(args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True, timeout=30)


def wait_result(unit, expected):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        logs = run(["journalctl", "-u", unit + ".service", "--output=cat", "--no-pager"]).stdout
        payloads = []
        for line in logs.splitlines():
            try:
                row = json.loads(line)
                if row.get("ok") is True and len(row.get("checks", [])) == 8:
                    payloads.append(row)
            except (ValueError, AttributeError):
                pass
        if len(payloads) >= expected:
            return len(payloads)
        time.sleep(0.5)
    raise RuntimeError("Transient timer did not produce expected successful harness results")


def main():
    if os.name != "posix" or os.geteuid() != 0:
        print(json.dumps({"unsupported": "Linux root/systemd only"}))
        return 2
    import grp
    os.umask(0o077)
    name = "backupcenter-native-validate-" + uuid4().hex[:12]
    root = Path("/run") / name
    root.mkdir(mode=0o750)
    root.chmod(0o750)
    group = grp.getgrnam("bareos").gr_gid
    os.chown(root, 0, group)
    for filename in ("check_after_job_native.py", "after_job_runtime.py"):
        target = root / filename
        shutil.copyfile(Path(__file__).with_name(filename), target)
        target.chmod(0o640)
        os.chown(target, 0, group)
    try:
        run(["systemd-run", "--unit=" + name, "--on-active=2s", "--on-unit-active=60s", "--timer-property=AccuracySec=100ms", "-p", "User=bareos", "-p", "Group=bareos", "-p", "UMask=0077", "-p", "NoNewPrivileges=true", "-p", "PrivateTmp=true", "-p", "ProtectSystem=strict", "-p", "ProtectHome=true", "/opt/bareos-api-venv/bin/python", str(root / "check_after_job_native.py")])
        first = wait_result(name, 1)
        run(["systemctl", "restart", name + ".timer"])
        second = wait_result(name, 2)
        print(json.dumps({"ok": True, "unit": name, "first_timer_invocations": first, "after_timer_restart_invocations": second, "fake_dispatch_only": True, "production_units_activated": False}))
        return 0
    finally:
        run(["systemctl", "stop", name + ".timer", name + ".service"], check=False)
        run(["systemctl", "reset-failed", name + ".timer", name + ".service"], check=False)
        for filename in ("check_after_job_native.py", "after_job_runtime.py"):
            (root / filename).unlink(missing_ok=True)
        cache = root / "__pycache__"
        # Bytecode is prevented by the read-only unit sandbox; do not recurse.
        if cache.exists():
            raise RuntimeError("Unexpected bytecode directory needs explicit inspection")
        root.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
