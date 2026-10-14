import asyncio
from fastapi.testclient import TestClient
from backend.app import app, Gateway, normalize, session


def example():
    return {"jobs": {"jobs": {"VMware-a": {"name": "VMware-a", "type": "Backup", "client": "proxy", "fileset": "VMware-a", "enabled": True, "password": "do-not-expose"}, "VMware-b": {"name": "VMware-b", "type": "Backup", "client": "proxy", "fileset": "VMware-b", "enabled": True}}}, "filesets": {"filesets": {"VMware-a": {"name": "VMware-a", "include": [{"plugin": ["python3:module_name=bareos-fd-vmware:vmname=a:folder=/Production:vcpass=do-not-expose"]}]}, "VMware-b": {"name": "VMware-b", "include": [{"plugin": ["python3:module_name=bareos-fd-vmware:vmname=b:folder=/Production"]}]}}}, "sessions": {"totalItems": "1", "jobs": [{"jobid": "11", "name": "VMware-a", "jobstatus": "T", "type": "B", "starttime": "2026-10-14 09:00:00", "endtime": "2026-10-14 09:05:00", "jobbytes": "42"}]}}


def test_vm_workloads_are_separate_from_shared_proxy_and_secrets():
    result = normalize(example(), {})
    assert [x["name"] for x in result["workloads"]] == ["a", "b"]
    assert all(x["proxy"] == "proxy" for x in result["workloads"])
    assert "do-not-expose" not in str(result)
    assert result["workloads"][0]["evidence"] == "Backup recorded"
    assert result["workloads"][1]["evidence"] == "No backup recorded"
    assert result["workloads"][0]["restoreVerified"] is False


def test_failed_session_source_is_unknown():
    assert all(w["evidence"] == "Unknown" for w in normalize(example(), {"sessions": "Unavailable"})["workloads"])


def test_restore_does_not_count_as_backup_evidence():
    data = example()
    data["sessions"]["jobs"][0]["type"] = "R"
    assert normalize(data, {})["workloads"][0]["backupCount"] == 0


def test_warnings_and_utc_conversion():
    s = session({"jobstatus": "T", "joberrors": "1", "starttime": "2026-10-14 09:00:00"})
    assert s["status"] == "Warning"
    assert s["started"].endswith("+00:00")
    assert session({"jobstatus": "?"})["status"] == "Unknown"


def test_mutations_and_foreign_origins_are_rejected():
    with TestClient(app) as client:
        assert client.post("/api/snapshot").status_code == 405
        assert client.get("/api/health", headers={"Origin": "https://foreign.example"}).status_code == 403
        assert client.get("/api/anything").status_code == 404
        assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_stale_snapshot_keeps_original_timestamp(monkeypatch):
    g = Gateway()
    g.restored_cache = True
    g.cached = {"syncedAt": "original", "connection": "connected", "workloads": []}
    async def fail(*args):
        raise RuntimeError("private diagnostic")
    monkeypatch.setattr(g, "get", fail)
    result = asyncio.run(g.snapshot(force=True))
    assert result["connection"] == "stale"
    assert result["syncedAt"] == "original"
    assert "private diagnostic" not in str(result)


def test_log_redaction():
    g = Gateway.__new__(Gateway)
    g.values = {"BAREOS_API_PASSWORD": "secret-value"}
    assert "secret-value" not in g.redact("authentication secret-value password=another-value")
    assert "another-value" not in g.redact("password=another-value")


def test_persisted_snapshot_restores_after_process_memory_loss(monkeypatch):
    async def scenario():
        g = Gateway()
        class FakeStore:
            configured = True
            def load(self):
                return {"syncedAt": "saved-time", "connection": "connected", "workloads": []}
            def status(self):
                return {"state": "connected"}
        g.store = FakeStore()
        async def fail(*args):
            raise RuntimeError("API offline")
        monkeypatch.setattr(g, "get", fail)
        value = await g.snapshot(force=True)
        assert value["connection"] == "stale"
        assert value["syncedAt"] == "saved-time"
    asyncio.run(scenario())


def test_restored_snapshot_always_attempts_live_refresh_even_with_new_clock(monkeypatch):
    async def scenario():
        g = Gateway()
        class FakeStore:
            configured = True
            def load(self): return {"syncedAt":"saved-time","connection":"connected","workloads":[]}
            def status(self): return {"state":"connected"}
        g.store=FakeStore()
        calls=[]
        async def offline(*args):
            calls.append(True)
            raise RuntimeError("offline")
        g.get=offline
        monkeypatch.setattr("backend.app.time.monotonic",lambda:0)
        result=await g.snapshot()
        assert calls
        assert result["connection"]=="stale"
        assert result["persistence"]["state"]=="connected"
    asyncio.run(scenario())
