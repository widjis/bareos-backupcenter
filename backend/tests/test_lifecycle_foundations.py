"""Production composition must preserve base operations and fail closed on missing DDL."""
from backend.lifecycle_foundations import compose_lifecycle_store, database_foundation_status


class Cursor:
    def __init__(self, absent=()):
        self.absent = absent
        self.query = ""
        self.params = ()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, query, params=()):
        self.query, self.params = query, params
    def fetchone(self):
        if "to_regclass" in self.query:
            return (self.params[0].split(".")[-1] not in self.absent,)
        if "has_table_privilege" in self.query: return (True,)
        return (7,)


class Connection:
    def __init__(self, absent=()): self.cur = Cursor(absent); self.closed = False
    def cursor(self): return self.cur
    def close(self): self.closed = True


class Base:
    connection_id = "test-connection"
    def __init__(self, absent=()): self.connection = Connection(absent)
    def connect(self): return self.connection
    def actor_allowed(self, actor, action): return actor == "admin" and action == "provision"


def test_composition_preserves_existing_base_store_behavior():
    base = Base()
    store, registry = compose_lifecycle_store(base)
    assert store.actor_allowed("admin", "provision") is True
    assert store.actor_allowed("viewer", "provision") is False
    assert store.connection_id == base.connection_id
    assert registry.store is base
    assert callable(store.begin)
    assert callable(store.create_retirement_operation)


def test_database_readiness_checks_exact_tables_and_closes_connection():
    base = Base()
    result = database_foundation_status(base)
    assert result == {"registryStoreReady": True, "durableStoreReady": True, "managedJobs": 7, "missingPrerequisites": []}
    assert base.connection.closed
    base = Base(("lifecycle_operations",))
    result = database_foundation_status(base)
    assert result["registryStoreReady"] is True
    assert result["durableStoreReady"] is False
    assert result["missingPrerequisites"] == ["lifecycle_operations"]


def test_unavailable_database_never_claims_ready_or_exposes_diagnostics():
    class Unavailable:
        def connect(self): raise RuntimeError("private connection data")
    result = database_foundation_status(Unavailable())
    assert result["registryStoreReady"] is False
    assert result["durableStoreReady"] is False
    assert "private" not in str(result)


def test_registry_route_admin_scope_and_sanitized_contract(monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from backend import app as module
    registry = SimpleNamespace(enumerate_entries=lambda: [{"stable_id": "stable", "job_name": "VMware-PNET", "instance_uuid": "vm-uuid", "repository_id": "SMB-PNET", "revision": 1, "lifecycle_state": "enabled", "proof_snapshot": {"private": "not for browser"}}])
    monkeypatch.setattr(module, "gateway", lambda: SimpleNamespace(lifecycle_registry=registry))
    with TestClient(module.app) as client:
        result = client.get("/api/jobs/lifecycle/registry")
        assert result.status_code == 200
        assert result.json()["count"] == 1
        assert result.json()["jobs"][0]["stableId"] == "stable"
        assert "private" not in result.text
        monkeypatch.setattr("backend.auth.session_user", lambda _: {"username": "viewer", "role": "Viewer"})
        assert client.get("/api/jobs/lifecycle/registry").status_code == 403
        assert client.get("/api/jobs/lifecycle/foundations").status_code == 403


async def _reconcile_case(monkeypatch, ready, observed, *, apply):
    from scripts import reconcile_managed_registry as command
    events = []
    class Repository:
        def __init__(self, store): pass
        def enumerate_entries(self):
            events.append("read_revision")
            return [{"stable_id": "stable", "revision": 4}]
        def read_retired_assignments(self): return []
        def reconcile(self, source, expected_revisions):
            events.append(("apply", expected_revisions))
            return {"id": "receipt", "status": "Applied"}
    async def collector():
        events.append("collect")
        return observed
    monkeypatch.setattr(command, "reconcile_managed_registry", lambda source, retired: {"status": source["status"], "entries": source["entries"], "blockers": source.get("blockers", [])})
    result, _ = await command.reconcile_live_registry(object(), apply=apply, collector=collector, repository_factory=Repository, readiness=lambda store: {"registryStoreReady": ready})
    return result, events


def test_registry_command_is_read_only_by_default_and_captures_revision_first(monkeypatch):
    import asyncio
    result, events = asyncio.run(_reconcile_case(monkeypatch, True, {"status": "ready", "entries": [1]}, apply=False))
    assert result["status"] == "ready"
    assert events == ["read_revision", "collect"]
    result, events = asyncio.run(_reconcile_case(monkeypatch, True, {"status": "ready", "entries": [1]}, apply=True))
    assert result["status"] == "Applied"
    assert events == ["read_revision", "collect", ("apply", {"stable": 4})]


def test_registry_command_never_writes_partial_proof_or_missing_schema(monkeypatch):
    import asyncio
    result, events = asyncio.run(_reconcile_case(monkeypatch, True, {"status": "blocked", "entries": [], "blockers": [{"code": "partial"}]}, apply=True))
    assert result["status"] == "blocked"
    assert events == ["read_revision", "collect"]
    result, events = asyncio.run(_reconcile_case(monkeypatch, False, {"status": "ready", "entries": [1]}, apply=True))
    assert result["status"] == "blocked"
    assert events == ["collect"]


def test_production_readiness_needs_explicit_gate_and_actual_schema(monkeypatch):
    from types import SimpleNamespace
    from backend import lifecycle_foundations as f
    collector = SimpleNamespace(collect_clone_review=lambda *args: {}, collect_retirement_proof=lambda *args: {})
    gateway = SimpleNamespace(store=object(), values={}, lifecycle_clone_collector=collector, lifecycle_retirement_collector=collector)
    monkeypatch.setattr(f, "database_foundation_status", lambda store: {"registryStoreReady": True, "durableStoreReady": True})
    calls = []
    def caps(values):
        calls.append(True)
        return {"installedReady": True, "transportReady": True, "applyEnabled": True}
    monkeypatch.setattr("backend.lifecycle_target.candidate_capabilities", caps)
    result = f.production_extra_readiness(gateway)
    assert result["durableStoreReady"] is True
    assert result["collectorReady"] is True
    assert result["executorReady"] is False and result["applyEnabled"] is False
    assert calls == []
    gateway.values["BACKUPCENTER_LIFECYCLE_APPLY_ENABLED"] = "1"
    result = f.production_extra_readiness(gateway)
    assert result["applyEnabled"] is True
    monkeypatch.setattr(f, "database_foundation_status", lambda store: {"registryStoreReady": True, "durableStoreReady": False})
    assert f.production_extra_readiness(gateway)["durableStoreReady"] is False
