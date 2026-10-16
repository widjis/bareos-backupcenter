import contextlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import integration.after_job_runtime as runtime

WITA = ZoneInfo("Asia/Makassar")


def at(value: str) -> datetime:
    hour, minute = map(int, value.split(":"))
    return datetime(2026, 10, 16, hour, minute, tzinfo=WITA)


def lock_factory():
    locks: dict[str, threading.Lock] = {}

    @contextlib.contextmanager
    def hold(path: Path):
        lock = locks.setdefault(str(path), threading.Lock())
        with lock:
            yield

    return hold


def read_receipt(tmp_path: Path) -> dict:
    path = next((tmp_path / "receipts").glob("*.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def test_trigger_rejects_unsafe_names_and_nonpositive_source_id(tmp_path):
    with pytest.raises(ValueError, match="source"):
        runtime.trigger(
            "vmware-pnet",
            7,
            "VMware-MTIMRWKF01",
            "configured",
            "22:00",
            state_dir=tmp_path,
            now=lambda: at("22:30"),
            query_active=lambda _: False,
            run_console=lambda *_: pytest.fail("console must stay idle"),
            lock_factory=lock_factory(),
        )
    with pytest.raises(ValueError, match="positive"):
        runtime.trigger(
            "VMware-PNET",
            0,
            "VMware-MTIMRWKF01",
            "configured",
            "22:00",
            state_dir=tmp_path,
            now=lambda: at("22:30"),
            query_active=lambda _: False,
            run_console=lambda *_: pytest.fail("console must stay idle"),
            lock_factory=lock_factory(),
        )


def test_before_window_is_durable_then_drain_queues_once_open(tmp_path):
    calls = []

    def runner(target, level):
        calls.append((target, level))
        return SimpleNamespace(stdout="Job queued. JobId=42", stderr="")

    receipt = runtime.trigger(
        "VMware-PNET",
        17,
        "VMware-MTIMRWKF01",
        "incremental",
        "23:00",
        "23:30",
        state_dir=tmp_path,
        now=lambda: at("22:15"),
        query_active=lambda _: False,
        run_console=runner,
        lock_factory=lock_factory(),
    )
    assert receipt["state"] == "Deferred" and receipt["deferredReason"] == "before_window"
    drained = runtime.drain(
        state_dir=tmp_path,
        now=lambda: at("23:05"),
        query_active=lambda _: False,
        run_console=runner,
        lock_factory=lock_factory(),
    )
    assert drained[0]["state"] == "Queued" and drained[0]["queuedJobId"] == 42
    assert calls == [("VMware-MTIMRWKF01", "incremental")]


def test_deferred_receipt_expires_after_window_without_running(tmp_path):
    runtime.trigger(
        "VMware-PNET",
        18,
        "VMware-MTIMRWKF01",
        "configured",
        "23:00",
        "23:10",
        state_dir=tmp_path,
        now=lambda: at("22:50"),
        query_active=lambda _: False,
        run_console=lambda *_: pytest.fail("console must stay idle"),
        lock_factory=lock_factory(),
    )
    drained = runtime.drain(
        state_dir=tmp_path,
        now=lambda: at("23:20"),
        query_active=lambda _: False,
        run_console=lambda *_: pytest.fail("console must stay idle"),
        lock_factory=lock_factory(),
    )
    assert drained[0]["state"] == "Expired"


def test_active_target_becomes_deferred_and_sql_errors_block(tmp_path):
    receipt = runtime.trigger(
        "VMware-PNET",
        19,
        "VMware-MTIMRWKF01",
        "configured",
        "22:00",
        state_dir=tmp_path,
        now=lambda: at("22:30"),
        query_active=lambda _: True,
        run_console=lambda *_: pytest.fail("console must stay idle"),
        lock_factory=lock_factory(),
    )
    assert receipt["state"] == "Deferred" and receipt["deferredReason"] == "active_target"
    with pytest.raises(RuntimeError, match="sql down"):
        runtime.trigger(
            "VMware-PNET",
            20,
            "VMware-MTIMRWKF01",
            "configured",
            "22:00",
            state_dir=tmp_path,
            now=lambda: at("22:30"),
            query_active=lambda _: (_ for _ in ()).throw(RuntimeError("sql down")),
            run_console=lambda *_: pytest.fail("console must stay idle"),
            lock_factory=lock_factory(),
        )


def test_rejected_ack_requires_one_positive_jobid_and_no_error(tmp_path):
    receipt = runtime.trigger(
        "VMware-PNET",
        21,
        "VMware-MTIMRWKF01",
        "configured",
        "22:00",
        state_dir=tmp_path,
        now=lambda: at("22:30"),
        query_active=lambda _: False,
        run_console=lambda *_: SimpleNamespace(stdout="Job queued. JobId=41\nJobId=42", stderr=""),
        lock_factory=lock_factory(),
    )
    assert receipt["state"] == "Unknown"
    assert "ambiguous" in receipt["message"]


def test_crash_after_dispatch_leaves_dispatching_and_never_auto_resends(tmp_path):
    calls = []

    def runner(target, level):
        calls.append((target, level))
        return SimpleNamespace(stdout="Job queued. JobId=77", stderr="")

    with pytest.raises(SystemExit):
        runtime.trigger(
            "VMware-PNET",
            22,
            "VMware-MTIMRWKF01",
            "configured",
            "22:00",
            state_dir=tmp_path,
            now=lambda: at("22:30"),
            query_active=lambda _: False,
            run_console=runner,
            lock_factory=lock_factory(),
            after_dispatch=lambda: (_ for _ in ()).throw(SystemExit(3)),
        )
    assert read_receipt(tmp_path)["state"] == "Dispatching"
    receipt = runtime.trigger(
        "VMware-PNET",
        22,
        "VMware-MTIMRWKF01",
        "configured",
        "22:00",
        state_dir=tmp_path,
        now=lambda: at("22:31"),
        query_active=lambda _: False,
        run_console=lambda *_: pytest.fail("console must stay idle"),
        lock_factory=lock_factory(),
    )
    assert receipt["state"] == "Dispatching"
    assert calls == [("VMware-MTIMRWKF01", "configured")]


def test_per_target_lock_and_receipt_dedup_allow_one_dispatch(tmp_path):
    calls = []
    gate = threading.Barrier(2)
    locks = lock_factory()

    def runner(target, level):
        calls.append((target, level))
        time.sleep(0.05)
        return SimpleNamespace(stdout="Job queued. JobId=88", stderr="")

    results = []

    def worker():
        gate.wait()
        results.append(
            runtime.trigger(
                "VMware-PNET",
                23,
                "VMware-MTIMRWKF01",
                "configured",
                "22:00",
                state_dir=tmp_path,
                now=lambda: at("22:30"),
                query_active=lambda _: False,
                run_console=runner,
                lock_factory=locks,
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == [("VMware-MTIMRWKF01", "configured")]
    assert [row["state"] for row in results] == ["Queued", "Queued"]


def test_deferred_receipt_expires_on_next_date(tmp_path):
    from datetime import timedelta
    kwargs=dict(state_dir=tmp_path,query_active=lambda _:False,run_console=lambda *_:pytest.fail("expired work must not run"),lock_factory=lock_factory())
    runtime.trigger("VMware-PNET",100,"VMware-MTIMRWKF01","configured","23:00",now=lambda:at("22:00"),**kwargs)
    rows=runtime.drain(now=lambda:at("23:10")+timedelta(days=1),**kwargs)
    assert rows[0]["state"]=="Expired"

def test_completed_queued_receipt_does_not_block_next_source_run(tmp_path):
    calls=[]
    kwargs=dict(state_dir=tmp_path,now=lambda:at("22:30"),query_active=lambda _:False,run_console=lambda *_:(calls.append(1) or SimpleNamespace(stdout="Job queued. JobId=42",stderr="")),lock_factory=lock_factory(),query_terminal=lambda row:row["queuedJobId"]==42)
    assert runtime.trigger("VMware-PNET",101,"VMware-MTIMRWKF01","configured","22:00",**kwargs)["state"]=="Queued"
    assert runtime.trigger("VMware-PNET",102,"VMware-MTIMRWKF01","configured","22:00",**kwargs)["state"]=="Queued"
    assert len(calls)==2

def test_unresolved_dispatch_blocks_a_different_source_run(tmp_path):
    kwargs=dict(state_dir=tmp_path,now=lambda:at("22:30"),query_active=lambda _:False,lock_factory=lock_factory())
    first=runtime.trigger("VMware-PNET",103,"VMware-MTIMRWKF01","configured","22:00",run_console=lambda *_:SimpleNamespace(stdout="JobId=42",stderr=""),**kwargs)
    assert first["state"]=="Unknown"
    second=runtime.trigger("VMware-PNET",104,"VMware-MTIMRWKF01","configured","22:00",run_console=lambda *_:pytest.fail("unresolved delivery"),**kwargs)
    assert second["state"]=="Deferred"

def test_empty_active_sql_result_is_not_inactive(monkeypatch):
    monkeypatch.setattr(runtime.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0,stdout="",stderr=""))
    with pytest.raises(ValueError,match="valid count"):
        runtime.query_active_target("VMware-PNET")

def test_nonzero_process_exit_cannot_be_acknowledged(tmp_path):
    row=runtime.trigger("VMware-PNET",105,"VMware-MTIMRWKF01","configured","22:00",state_dir=tmp_path,now=lambda:at("22:30"),query_active=lambda _:False,run_console=lambda *_:SimpleNamespace(returncode=1,stdout="Job queued. JobId=42",stderr=""),lock_factory=lock_factory())
    assert row["state"]=="Unknown"
