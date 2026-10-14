from uuid import uuid4

from fastapi.testclient import TestClient

from backend import app as module
from backend.tests.test_operations import HEADERS


VM_ID = "12345678-1234-1234-1234-123456789abc"
INVENTORY_ID = "11111111-1111-1111-1111-111111111111"


class FakeInventory:
    async def snapshot(self, refresh=False):
        return {
            "state": "connected",
            "persistence": "connected",
            "error": None,
            "syncedAt": "2026-10-15T10:00:00+00:00",
            "folders": [],
            "vms": [
                {
                    "id": INVENTORY_ID,
                    "name": "safe-vm",
                    "moref": "vm-123",
                    "instanceUuid": VM_ID,
                    "folder": "/Production",
                    "folderId": "group-v1",
                    "ancestorIds": ["group-v1"],
                    "datacenter": "DC1",
                    "power": "poweredOn",
                    "template": False,
                    "host": "esx1",
                    "cpu": 2,
                    "memoryMb": 4096,
                }
            ],
            "scope": "Objects visible to the configured VMware account",
        }


class FakeStore:
    configured = True

    def __init__(self):
        self.prepared = None
        self.assignments = {}

    def operation_key(self, key):
        return self.prepared if self.prepared and self.prepared["idempotency_key"] == str(key) else None

    def prepare_provisioning(self, key, actor, plan):
        self.prepared = {
            "id": str(uuid4()),
            "idempotency_key": str(key),
            "kind": "provision",
            "target": str(uuid4()),
            "state": "Prepared",
            "job_id": None,
            "actor": actor,
            "parameters": {
                "summary": f"{len(plan['changes'])} VM{'s' if len(plan['changes']) != 1 else ''} · {plan['policy']['name']}",
                "simulationOnly": True,
            },
            "created_at": "2026-10-15T10:00:00+00:00",
            "updated_at": "2026-10-15T10:00:00+00:00",
        }
        return self.prepared

    def assignment_map(self):
        return self.assignments


class FakeGateway:
    def __init__(self):
        self.store = FakeStore()

    async def snapshot(self, refresh=False):
        return {
            "connection": "connected",
            "sourceErrors": {},
            "storages": [{"name": "VeeamSMB", "mediaType": "SMBFile", "enabled": True}],
            "jobs": [],
            "workloads": [{"job": "MTIMRWCNTDEV"}],
            "capabilities": {"controls": False},
            "persistence": {"state": "connected"},
        }


def test_provisioning_apply_stages_a_dry_run_operation(monkeypatch):
    gateway = FakeGateway()
    monkeypatch.setattr(module, "gateway", lambda: gateway)
    monkeypatch.setattr(module, "inventory", lambda: FakeInventory())
    body = {
        "vm_ids": [INVENTORY_ID],
        "storage": "VeeamSMB",
        "policy_id": None,
        "policy_revision": 0,
        "idempotency_key": str(uuid4()),
        "confirmed": True,
    }
    with TestClient(module.app) as client:
        response = client.post("/api/provisioning/apply", headers=HEADERS, json=body)
        assert response.status_code == 202
        payload = response.json()
        assert payload["kind"] == "provision"
        assert payload["parameters"]["simulationOnly"] is True
        assert gateway.store.prepared is not None


def test_provisioning_apply_plan_includes_script_review(monkeypatch):
    gateway = FakeGateway()
    captured = {}
    original_prepare = gateway.store.prepare_provisioning

    def prepare(key, actor, plan):
        captured["plan"] = plan
        return original_prepare(key, actor, plan)

    gateway.store.prepare_provisioning = prepare
    monkeypatch.setattr(module, "gateway", lambda: gateway)
    monkeypatch.setattr(module, "inventory", lambda: FakeInventory())
    body = {
        "vm_ids": [INVENTORY_ID],
        "storage": "VeeamSMB",
        "policy_id": None,
        "policy_revision": 0,
        "idempotency_key": str(uuid4()),
        "confirmed": True,
    }
    with TestClient(module.app) as client:
        response = client.post("/api/provisioning/apply", headers=HEADERS, json=body)
        assert response.status_code == 202
        assert captured["plan"]["scriptReview"]["baselineCount"] == 1
        assert captured["plan"]["scriptReview"]["additions"][0]["job"].startswith("BC-")


def test_inventory_route_shows_prepared_assignment_overlay(monkeypatch):
    gateway = FakeGateway()
    gateway.store.assignments = {
        INVENTORY_ID: {"inventory_vm_id": INVENTORY_ID, "job_name": "BC-safe-vm", "state": "Prepared"}
    }
    monkeypatch.setattr(module, "gateway", lambda: gateway)
    monkeypatch.setattr(module, "inventory", lambda: FakeInventory())
    with TestClient(module.app) as client:
        response = client.get("/api/inventory")
        assert response.status_code == 200
        row = response.json()["vms"][0]
        assert row["association"] == "Prepared assignment"
        assert row["job"] == "BC-safe-vm"
        assert row["backupEvidence"] == "Pending controlled apply"
