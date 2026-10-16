"""Integration guards for lifecycle wiring and truthful operation outcomes."""
import asyncio
from uuid import uuid4

import pytest
from backend.tests.test_lifecycle_api import lifecycle_env, HEADERS
from backend.tests.test_lifecycle_extra_api import CombinedStore, Gateway, _client
from backend.operations import dispatch
from integration import apply_job_lifecycle as helper


@pytest.mark.parametrize("outcome, expected", [("Failed", "Failed"), ("Unknown", "Unknown"), (None, "Unknown")])
def test_worker_never_reports_non_applied_helper_as_success(lifecycle_env, monkeypatch, outcome, expected):
    client, gateway, _, _, _ = lifecycle_env
    review = client.post("/api/jobs/lifecycle/disable/review", headers=HEADERS, json={"jobName": "VMware-PNET"}).json()
    response = client.post("/api/jobs/lifecycle/disable", headers=HEADERS, json={"jobName": "VMware-PNET", "idempotencyKey": str(uuid4()), "reviewDigest": review["reviewDigest"], "proofRevision": review["proofRevision"], "confirmed": True})
    assert response.status_code == 202
    calls = []
    monkeypatch.setattr(helper, "apply", lambda body: calls.append(body) or {"state": outcome})
    asyncio.run(dispatch(gateway, response.json()))
    asyncio.run(dispatch(gateway, response.json()))
    assert len(calls) == 1
    assert gateway.store.rows[response.json()["id"]]["state"] == expected
    assert gateway.store.last_revision is None or gateway.store.last_revision["state"] != "Validated"


def test_main_app_registers_extra_routes_and_rejects_browser_proof(lifecycle_env):
    client, _, _, _, _ = lifecycle_env
    body = {"sourceJobName": "VMware-PNET", "newJobName": "VMware-LAB"}
    response = client.post("/api/jobs/lifecycle/clone/review", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert response.json()["executionSupported"] is False
    assert response.json()["blockers"]
    assert client.post("/api/jobs/lifecycle/clone/review", headers=HEADERS, json={**body, "proof": {"complete": True}}).status_code == 422
    assert client.post("/api/jobs/lifecycle/remove/review", headers=HEADERS, json={"jobName": "VMware-PNET"}).status_code == 200
    assert client.post("/api/jobs/lifecycle/remove/review", json={"jobName": "VMware-PNET"}).status_code == 403


def test_enable_unavailable_native_proof_is_a_blocked_review(lifecycle_env, monkeypatch):
    client, _, _, _, _ = lifecycle_env
    monkeypatch.setattr("backend.lifecycle_manager._current", lambda _: (_ for _ in ()).throw(RuntimeError("private native detail")))
    response = client.post("/api/jobs/lifecycle/enable/review", headers=HEADERS, json={"jobName": "VMware-PNET"})
    assert response.status_code == 200
    assert response.json()["readiness"] == "blocked"
    assert "private native detail" not in response.text


def test_extra_status_returns_no_before_images_or_candidate_configuration():
    store = CombinedStore()
    key = str(uuid4())
    store.clone_records[key] = {"state": "Unknown", "newJobName": "VMware-LAB", "response": {"summary": "Reconcile", "nativeCandidate": {"private": "hidden"}}}
    store.retire_key_map[key] = "op"
    store.retire_ops["op"] = {"intent": {"jobName": "VMware-PNET"}, "result": {"readiness": "unknown", "summary": "Reconcile", "beforeImage": "private"}}
    client = _client(Gateway(store, ready=False))
    for action in ("clone", "remove"):
        response = client.get(f"/api/jobs/lifecycle/{action}/status/{key}")
        assert response.status_code == 200
        assert response.json()["state"] == "Unknown"
        assert "private" not in response.text
        assert client.get(f"/api/jobs/lifecycle/{action}/status/{key}", headers={"x-role": "Viewer"}).status_code == 403


def test_native_write_requires_root_before_any_dependency_or_effect(monkeypatch):
    monkeypatch.setattr(helper.os, "geteuid", lambda: 1000, raising=False)
    with pytest.raises(ValueError, match="Root-owned"):
        helper.apply({})
