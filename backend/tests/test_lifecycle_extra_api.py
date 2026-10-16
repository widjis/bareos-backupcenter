from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.lifecycle_extra_api import create_lifecycle_extra_router


POST_HEADERS = {"origin": "http://127.0.0.1:3000", "x-backup-center-action": "confirmed"}


def _retirement_proof(**overrides):
    data = {
        "jobName": "VMware-PNET",
        "stableId": "managed.pnet",
        "vmInstanceUuid": "11111111-1111-1111-1111-111111111111",
        "repositoryId": "repo-primary",
        "proofRevision": 7,
        "jobRevision": 41,
        "stableVmRevision": 12,
        "repositoryRevision": 9,
        "configurationRevisionId": "cfg-0001",
        "resources": [
            {"resourceType": "job", "resourceName": "VMware-PNET", "ownership": "exclusive", "usageCount": 1},
            {"resourceType": "fileset", "resourceName": "VMware-PNET", "ownership": "exclusive", "usageCount": 1},
            {"resourceType": "pool", "resourceName": "PNET", "ownership": "shared", "usageCount": 2},
            {"resourceType": "storage", "resourceName": "repo-primary", "ownership": "shared", "usageCount": 7},
        ],
        "operations": [],
        "dependencies": [],
        "runtime": {
            "jobConfigPath": "",
            "jobConfigDigest": "",
            "jobConfigOwned": True,
            "exactJobFile": True,
            "ownershipVerified": True,
            "hooksVerified": True,
            "runtimeReadbackVerified": True,
            "hookReferences": [],
        },
        "retainedRecovery": {
            "recoveryPointCount": 2,
            "latestJobIds": [23, 24],
            "catalogReferenceIds": ["catalog:23", "catalog:24"],
            "catalogVisibilityConfirmed": True,
            "stableRecoveryReferencesConfirmed": True,
            "retentionOwnerConfirmed": True,
            "cleanupOwnerConfirmed": True,
            "mediaReadableVerified": False,
        },
    }
    data.update(overrides)
    return data


class CombinedStore:
    def __init__(self):
        self.allow_actor = True
        self.clone_records = {}
        self.retire_ops = {}
        self.retire_key_map = {}
        self.retire_records = {}

    def actor_allowed(self, username, kind):
        return self.allow_actor and kind == "provision"

    def get_intent(self, intent_id):
        return deepcopy(self.clone_records.get(intent_id))

    def begin(self):
        return CloneTx(self)

    def load_retirement_operation(self, idempotency_key):
        op_id = self.retire_key_map.get(idempotency_key)
        return deepcopy(self.retire_ops.get(op_id))

    def create_retirement_operation(self, intent):
        row = {"id": intent["id"], "intent": deepcopy(intent), "result": {"jobName": intent["jobName"], "readiness": "prepared"}}
        self.retire_ops[row["id"]] = row
        self.retire_key_map[intent["idempotencyKey"]] = row["id"]
        return deepcopy(row)

    def save_retirement_record(self, operation_id, record):
        self.retire_records[record["jobName"]] = deepcopy(record)
        return deepcopy(record)

    def finalize_retirement_operation(self, operation_id, state, result):
        self.retire_ops[operation_id]["result"] = deepcopy(result)
        record = self.retire_records.get(result["jobName"])
        if record:
            record["state"] = state
            record["retiredAt"] = result["retirementRecord"].get("retiredAt")
        return deepcopy(self.retire_ops[operation_id])

    def load_retirement_record(self, job_name):
        return deepcopy(self.retire_records.get(job_name))


class CloneTx:
    def __init__(self, store):
        self.store = store
        self.pending = {}

    def insert_intent(self, intent_id, record):
        self.pending[intent_id] = deepcopy(record)

    def update_intent(self, intent_id, record):
        self.pending[intent_id] = deepcopy(record)

    def read_intent(self, intent_id):
        return deepcopy(self.pending[intent_id])

    def commit(self):
        for intent_id, record in self.pending.items():
            self.store.clone_records[intent_id] = deepcopy(record)

    def rollback(self):
        self.pending = {}


class CloneCollector:
    def __init__(self):
        self.snapshot_revision = 7
        self.raise_error = False

    def collect_clone_review(self, source_job_name, new_job_name, new_vm_uuid, repository_id, trusted_role):
        if self.raise_error:
            raise RuntimeError("collector exploded")
        source_vm = "11111111-1111-1111-1111-111111111111"
        return {
            "snapshot": {
                "stable_id": "managed.pnet",
                "job_name": source_job_name,
                "selection_revision": self.snapshot_revision,
                "snapshot_revision": self.snapshot_revision,
                "identity_revision": 12,
                "managed_vm_ids": [source_vm],
                "repository_id": "repo-PNET",
            },
            "registryEvidence": {
                "proof_revision": self.snapshot_revision,
                "proof_coverage": ["assignments", "dependencies", "intents", "names", "operations", "resources", "target_repository", "target_vm"],
                "existing_job_names": [source_job_name],
                "existing_assignments": [{"job_name": source_job_name, "vm_identity": source_vm, "stable_id": "managed.pnet", "state": "managed"}],
                "resources": [],
                "operations": [],
                "dependencies": [],
                "unresolved_intents": [],
                "repositories": [{"id": repository_id, "label": repository_id.removeprefix("repo-"), "supported": True}],
                "source_assignment": {
                    "stable_id": "managed.pnet",
                    "job_name": source_job_name,
                    "vm_identity": source_vm,
                    "repository_id": "repo-PNET",
                },
            },
            "resourceOwnership": [{"resourceType": "job", "resourceName": source_job_name, "ownership": "exclusive"}],
            "duplicateProtection": {"existingJobNames": [source_job_name], "sourceStableId": "managed.pnet"},
            "unsupportedChanges": ["Secret copying remains blocked."],
        }


class CloneExecutor:
    def __init__(self, state="applied"):
        self.state = state

    def apply_clone(self, native_candidate, *, actor, intent_id):
        return {"state": self.state, "summary": f"Clone {self.state} for {actor} via {intent_id}."}


class RetirementExecutor:
    def __init__(self, tmp_path, proof, *, fail_readback=False, fail_restore=False):
        self.job_path = tmp_path / "job" / "VMware-PNET.conf"
        self.job_path.parent.mkdir(parents=True, exist_ok=True)
        self.job_path.write_text('Job { Name = "VMware-PNET" }\n', encoding="utf-8")
        self.fail_readback = fail_readback
        self.fail_restore = fail_restore
        self.readback_calls = 0
        proof["runtime"]["jobConfigPath"] = str(self.job_path)
        proof["runtime"]["jobConfigDigest"] = self._digest(self.job_path.read_text(encoding="utf-8"))

    @staticmethod
    def _digest(text):
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def capture_job_config(self, job_name):
        text = self.job_path.read_text(encoding="utf-8")
        return {"path": str(self.job_path), "digest": self._digest(text), "content": text, "exists": True}

    def delete_job_config(self, job_name, *, expected_path, expected_digest):
        assert str(self.job_path) == expected_path
        assert self.capture_job_config(job_name)["digest"] == expected_digest
        self.job_path.unlink()
        return {"removed": True, "path": expected_path}

    def read_job_config(self, job_name):
        self.readback_calls += 1
        if self.fail_readback and self.readback_calls == 1:
            return {"exists": True, "path": str(self.job_path), "digest": None}
        if not self.job_path.exists():
            return {"exists": False, "path": str(self.job_path), "digest": None}
        text = self.job_path.read_text(encoding="utf-8")
        return {"exists": True, "path": str(self.job_path), "digest": self._digest(text)}

    def restore_job_config(self, beforeimage):
        if self.fail_restore:
            return {"restored": False}
        Path(beforeimage["path"]).write_text(beforeimage["content"], encoding="utf-8")
        return {"restored": True}


class RetirementCollector:
    def __init__(self, proof):
        self.proof = proof

    def collect_retirement_proof(self, job_name, trusted_role):
        assert trusted_role == "Admin"
        assert job_name == self.proof["jobName"]
        return deepcopy(self.proof)


class Gateway:
    def __init__(self, store, *, clone_collector=None, clone_executor=None, retirement_collector=None, retirement_executor=None, ready=True):
        self.store = store
        self.lifecycle_clone_collector = clone_collector
        self.lifecycle_clone_executor = clone_executor
        self.lifecycle_retirement_collector = retirement_collector
        self.lifecycle_retirement_executor = retirement_executor
        self.lifecycle_extra_readiness = {
            "installedReady": ready,
            "transportReady": ready,
            "collectorReady": ready,
            "durableStoreReady": ready,
            "executorReady": ready,
        }


def _client(gateway):
    app = FastAPI()

    @app.middleware("http")
    async def inject_user(request, call_next):
        request.state.user = {"role": request.headers.get("x-role", "Admin"), "username": request.headers.get("x-user", "admin")}
        return await call_next(request)

    app.include_router(create_lifecycle_extra_router(lambda: gateway))
    return TestClient(app)


def test_clone_review_missing_selected_vm_and_repository_is_helpful_block():
    client = _client(Gateway(CombinedStore(), ready=False))
    response = client.post("/api/jobs/lifecycle/clone/review", headers=POST_HEADERS, json={"sourceJobName": "VMware-PNET", "newJobName": "VMware-LAB"})
    assert response.status_code == 200
    data = response.json()
    assert data["proofRevision"] == 0
    assert {"missing_selected_vm", "missing_repository"} <= {item["code"] for item in data["blockers"]}


def test_wrong_body_proof_rejected_and_default_remove_prereqs_blocked():
    client = _client(Gateway(CombinedStore(), ready=False))
    review = client.post("/api/jobs/lifecycle/clone/review", headers=POST_HEADERS, json={"sourceJobName": "VMware-PNET", "newJobName": "VMware-LAB", "registryEvidence": {}})
    assert review.status_code == 422
    blocked = client.post("/api/jobs/lifecycle/remove/review", headers=POST_HEADERS, json={"jobName": "VMware-PNET"})
    assert blocked.status_code == 200
    assert blocked.json()["proofRevision"] == 0
    apply = client.post(
        "/api/jobs/lifecycle/remove",
        headers=POST_HEADERS,
        json={"jobName": "VMware-PNET", "reviewDigest": "a" * 64, "proofRevision": 1, "idempotencyKey": str(uuid4()), "confirmed": True},
    )
    assert apply.status_code == 409


def test_clone_review_apply_replay_and_stale_rejection():
    store = CombinedStore()
    collector = CloneCollector()
    client = _client(Gateway(store, clone_collector=collector, clone_executor=CloneExecutor(), ready=True))
    review = client.post(
        "/api/jobs/lifecycle/clone/review",
        headers=POST_HEADERS,
        json={"sourceJobName": "VMware-PNET", "newJobName": "VMware-LAB", "newVmUuid": "22222222-2222-2222-2222-222222222222", "repositoryId": "repo-LAB"},
    )
    assert review.status_code == 200
    review_data = review.json()
    assert review_data["readiness"] == "candidate_ready"
    payload = {
        "sourceJobName": "VMware-PNET",
        "newJobName": "VMware-LAB",
        "newVmUuid": "22222222-2222-2222-2222-222222222222",
        "repositoryId": "repo-LAB",
        "idempotencyKey": str(uuid4()),
        "reviewDigest": review_data["reviewDigest"],
        "proofRevision": review_data["proofRevision"],
        "confirmed": True,
    }
    first = client.post("/api/jobs/lifecycle/clone", headers=POST_HEADERS, json=payload)
    second = client.post("/api/jobs/lifecycle/clone", headers=POST_HEADERS, json=payload)
    assert first.status_code == 202 == second.status_code
    assert first.json()["intentId"] == second.json()["intentId"]
    collector.snapshot_revision = 8
    stale = client.post("/api/jobs/lifecycle/clone", headers=POST_HEADERS, json={**payload, "idempotencyKey": str(uuid4())})
    assert stale.status_code == 409


def test_clone_apply_rechecks_actor_and_can_return_unknown():
    store = CombinedStore()
    collector = CloneCollector()
    client = _client(Gateway(store, clone_collector=collector, clone_executor=CloneExecutor(state="unknown"), ready=True))
    review = client.post(
        "/api/jobs/lifecycle/clone/review",
        headers=POST_HEADERS,
        json={"sourceJobName": "VMware-PNET", "newJobName": "VMware-LAB", "newVmUuid": "22222222-2222-2222-2222-222222222222", "repositoryId": "repo-LAB"},
    ).json()
    store.allow_actor = False
    denied = client.post(
        "/api/jobs/lifecycle/clone",
        headers=POST_HEADERS,
        json={
            "sourceJobName": "VMware-PNET",
            "newJobName": "VMware-LAB",
            "newVmUuid": "22222222-2222-2222-2222-222222222222",
            "repositoryId": "repo-LAB",
            "idempotencyKey": str(uuid4()),
            "reviewDigest": review["reviewDigest"],
            "proofRevision": review["proofRevision"],
            "confirmed": True,
        },
    )
    assert denied.status_code == 403
    store.allow_actor = True
    unknown = client.post(
        "/api/jobs/lifecycle/clone",
        headers=POST_HEADERS,
        json={
            "sourceJobName": "VMware-PNET",
            "newJobName": "VMware-LAB",
            "newVmUuid": "22222222-2222-2222-2222-222222222222",
            "repositoryId": "repo-LAB",
            "idempotencyKey": str(uuid4()),
            "reviewDigest": review["reviewDigest"],
            "proofRevision": review["proofRevision"],
            "confirmed": True,
        },
    )
    assert unknown.status_code == 202
    assert unknown.json()["readiness"] == "unknown"


def test_remove_review_apply_and_retired_discovery(tmp_path):
    store = CombinedStore()
    proof = _retirement_proof()
    executor = RetirementExecutor(tmp_path, proof)
    client = _client(
        Gateway(
            store,
            retirement_collector=RetirementCollector(proof),
            retirement_executor=executor,
            ready=True,
        )
    )
    review = client.post("/api/jobs/lifecycle/remove/review", headers=POST_HEADERS, json={"jobName": "VMware-PNET"})
    assert review.status_code == 200
    review_data = review.json()
    assert review_data["readiness"] == "candidate_ready"
    apply = client.post(
        "/api/jobs/lifecycle/remove",
        headers=POST_HEADERS,
        json={
            "jobName": "VMware-PNET",
            "idempotencyKey": str(uuid4()),
            "reviewDigest": review_data["reviewDigest"],
            "proofRevision": review_data["proofRevision"],
            "confirmed": True,
        },
    )
    assert apply.status_code == 202
    result = apply.json()
    assert result["readiness"] == "applied"
    retired = client.get("/api/jobs/lifecycle/retired", params={"jobName": "VMware-PNET"})
    assert retired.status_code == 200
    assert retired.json()["retainedRecovery"]["mediaReadableVerified"] is False


def test_remove_apply_unknown_and_stale_review(tmp_path):
    store = CombinedStore()
    proof = _retirement_proof()
    executor = RetirementExecutor(tmp_path, proof, fail_readback=True, fail_restore=True)
    collector = RetirementCollector(proof)
    client = _client(Gateway(store, retirement_collector=collector, retirement_executor=executor, ready=True))
    review = client.post("/api/jobs/lifecycle/remove/review", headers=POST_HEADERS, json={"jobName": "VMware-PNET"}).json()
    stale_proof = deepcopy(proof)
    stale_proof["proofRevision"] = 8
    stale_proof["runtime"]["jobConfigDigest"] = "b" * 64
    collector.proof = stale_proof
    stale = client.post(
        "/api/jobs/lifecycle/remove",
        headers=POST_HEADERS,
        json={
            "jobName": "VMware-PNET",
            "idempotencyKey": str(uuid4()),
            "reviewDigest": review["reviewDigest"],
            "proofRevision": review["proofRevision"],
            "confirmed": True,
        },
    )
    assert stale.status_code == 409
    collector.proof = proof
    unknown = client.post(
        "/api/jobs/lifecycle/remove",
        headers=POST_HEADERS,
        json={
            "jobName": "VMware-PNET",
            "idempotencyKey": str(uuid4()),
            "reviewDigest": review["reviewDigest"],
            "proofRevision": review["proofRevision"],
            "confirmed": True,
        },
    )
    assert unknown.status_code == 202
    assert unknown.json()["readiness"] == "unknown"
