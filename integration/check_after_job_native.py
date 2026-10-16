import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

WITA = ZoneInfo("Asia/Makassar")


def jdump(value):
    print(json.dumps(value, sort_keys=True))


def load_runtime():
    path = Path(__file__).with_name("after_job_runtime.py")
    spec = importlib.util.spec_from_file_location("after_job_runtime", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jread(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def jwrite(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True))


def mode_bits(path):
    return stat.S_IMODE(Path(path).stat().st_mode)


def log_dispatch(shared, target, level):
    fd = os.open(str(Path(shared) / "dispatch.log"), os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        os.write(fd, f"{target}|{level}\n".encode())
    finally:
        os.close(fd)


def child():
    runtime = load_runtime()
    shared = Path(sys.argv[2])
    now = lambda: datetime.fromisoformat(sys.argv[3]).replace(tzinfo=WITA)
    cfg = lambda: jread(shared / "cfg.json", {})

    def active(_target):
        value = cfg().get("active", 0)
        if value == "error":
            raise RuntimeError("fake sql error")
        return bool(value)

    def console(target, level):
        current = cfg()
        log_dispatch(shared, target, level)
        time.sleep(current.get("delay", 0))
        mode = current.get("console", "ack")
        if mode == "raise":
            raise RuntimeError("fake bconsole failure")
        return SimpleNamespace(returncode=0, stdout=f"Job queued\nJobId={current.get('jobid', 101)}", stderr="")

    def terminal(row):
        return bool(cfg().get("terminal", {}).get(str(row["queuedJobId"]), False))

    crash = cfg().get("crash_after_dispatch", False)
    kwargs = dict(state_dir=shared / "state", now=now, query_active=active, run_console=console, query_terminal=terminal)
    if crash:
        kwargs["after_dispatch"] = lambda: os._exit(91)
    if sys.argv[1] == "trigger":
        result = runtime.trigger(sys.argv[4], int(sys.argv[5]), sys.argv[6], sys.argv[7], sys.argv[8], sys.argv[9] if sys.argv[9] != "-" else None, **kwargs)
    else:
        result = runtime.drain(state_dir=shared / "state", now=now, query_active=active, run_console=console, query_terminal=terminal, target=None if sys.argv[4] == "-" else sys.argv[4])
    jdump(result)


def run_child(*args):
    result = subprocess.run([sys.executable, __file__, *args], text=True, capture_output=True, timeout=25)
    return result.returncode, json.loads(result.stdout.strip() or "{}"), result.stderr.strip()


def popen_child(*args):
    return subprocess.Popen([sys.executable, __file__, *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def read_receipts(shared):
    root = Path(shared) / "state" / "receipts"
    return [json.loads(path.read_text()) for path in sorted(root.glob("*.json"))]


def expect(ok, message):
    if not ok:
        raise AssertionError(message)


def scenario_identical(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 201, "delay": 0.3})
    args = ("trigger", shared, "2026-10-16T22:10:00", "VMware-PNET", "17", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    left = popen_child(*args)
    right = popen_child(*args)
    a = json.loads(left.communicate(timeout=25)[0].strip())
    b = json.loads(right.communicate(timeout=25)[0].strip())
    expect(a["state"] == b["state"] == "Queued", "identical triggers must both observe one queued receipt")
    expect(len((Path(shared) / "dispatch.log").read_text().splitlines()) == 1, "identical triggers dispatched more than once")
    return {"name": "identical_dispatch_once", "ok": True, "queuedJobId": a["queuedJobId"]}


def scenario_distinct_sources(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 209, "delay": 0.3})
    args = ["trigger", shared, "2026-10-16T22:10:00", "VMware-PNET", "27", "VMware-MTIMRWKF01", "configured", "22:00", "-"]
    left = popen_child(*args); args[3] = "VMware-MTIMRWCNTDEV"; args[4] = "28"; right = popen_child(*args)
    rows = [json.loads(proc.communicate(timeout=25)[0].strip()) for proc in (left, right)]
    expect(sorted(row["state"] for row in rows) == ["Deferred", "Queued"], "per-target lock must serialize distinct sources")
    expect(len((Path(shared) / "dispatch.log").read_text().splitlines()) == 1, "distinct sources double-dispatched target")
    return {"name": "distinct_sources_serialized", "ok": True}


def scenario_crash(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 202, "crash_after_dispatch": True})
    code = subprocess.run([sys.executable, __file__, "trigger", shared, "2026-10-16T22:11:00", "VMware-PNET", "18", "VMware-MTIMRWKF01", "configured", "22:00", "-"]).returncode
    expect(code == 91, "crash child did not exit with the expected crash code")
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 203})
    _, row, _ = run_child("trigger", shared, "2026-10-16T22:12:00", "VMware-PNET", "18", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    expect(row["state"] == "Dispatching", "crashed dispatch must remain Dispatching")
    expect(len((Path(shared) / "dispatch.log").read_text().splitlines()) == 1, "Dispatching receipt was resent")
    return {"name": "crash_keeps_dispatching", "ok": True}


def scenario_expiry(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 204})
    _, row, _ = run_child("trigger", shared, "2026-10-16T22:00:00", "VMware-PNET", "19", "VMware-MTIMRWKF01", "configured", "23:00", "23:30")
    expect(row["state"] == "Deferred", "before-window trigger must defer")
    _, drained, _ = run_child("drain", shared, "2026-10-17T23:05:00", "-")
    expect(drained[0]["state"] == "Expired", "old deferred receipt must expire on the next date")
    return {"name": "old_date_deferred_expiry", "ok": True}


def scenario_deferred_delivery(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 210})
    _, before, _ = run_child("trigger", shared, "2026-10-16T22:00:00", "VMware-PNET", "29", "VMware-MTIMRWKF01", "configured", "23:00", "23:30")
    expect(before["state"] == "Deferred", "early work must be retained")
    _, rows, _ = run_child("drain", shared, "2026-10-16T23:10:00", "-")
    expect(rows[0]["state"] == "Queued" and rows[0]["queuedJobId"] == 210, "open window must deliver deferred work")
    expect(len((Path(shared) / "dispatch.log").read_text().splitlines()) == 1, "deferred work must dispatch once")
    return {"name": "deferred_delivered_in_window", "ok": True}


def scenario_reconcile(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 205})
    run_child("trigger", shared, "2026-10-16T22:13:00", "VMware-PNET", "20", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 206, "terminal": {"205": True}})
    _, row, _ = run_child("trigger", shared, "2026-10-16T22:14:00", "VMware-MTIMRWCNTDEV", "21", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    states = {item["sourceJobId"]: item["state"] for item in read_receipts(shared)}
    expect(states[20] == "Completed" and row["state"] == "Queued", "queued-terminal reconciliation failed")
    return {"name": "queued_terminal_reconciliation", "ok": True}


def scenario_unknown(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "raise"})
    run_child("trigger", shared, "2026-10-16T22:15:00", "VMware-PNET", "22", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 207})
    _, row, _ = run_child("trigger", shared, "2026-10-16T22:16:00", "VMware-MTIMRWCNTDEV", "23", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    expect(row["state"] == "Deferred" and row["deferredReason"] == "target_pending", "Unknown receipt did not block a new trigger")
    return {"name": "unknown_blocks_new", "ok": True}


def scenario_permissions(shared):
    jwrite(Path(shared) / "cfg.json", {"console": "ack", "jobid": 208})
    run_child("trigger", shared, "2026-10-16T22:17:00", "VMware-PNET", "24", "VMware-MTIMRWKF01", "configured", "22:00", "-")
    state = Path(shared) / "state"
    receipt = next((state / "receipts").glob("*.json"))
    expect(mode_bits(state / "receipts") == 0o700 and mode_bits(state / "locks") == 0o700, "runtime directories are not 0700")
    expect(mode_bits(receipt) == 0o600, "receipt is not 0600")
    return {"name": "permissions", "ok": True}


def main():
    if os.name != "posix":
        jdump({"ok": False, "unsupported": "posix-only"})
        return 2
    if len(sys.argv) > 1 and sys.argv[1] in {"trigger", "drain"}:
        child()
        return 0
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix="after-job-native-") as td:
            for name, fn in (
                ("identical", scenario_identical),
                ("distinct", scenario_distinct_sources),
                ("crash", scenario_crash),
                ("expiry", scenario_expiry),
                ("delivery", scenario_deferred_delivery),
                ("reconcile", scenario_reconcile),
                ("unknown", scenario_unknown),
                ("permissions", scenario_permissions),
            ):
                shared = Path(td) / name
                shared.mkdir()
                results.append(fn(str(shared)))
        jdump({"ok": True, "checks": results})
        return 0
    except Exception as exc:
        jdump({"ok": False, "checks": results, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
