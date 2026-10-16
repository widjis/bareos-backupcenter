from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from backend.lifecycle_retirement import execute_retirement, retired_job_discovery, review_retirement


def _proof(**overrides):
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
            {"resourceType": "schedule", "resourceName": "BC-Policy-PNET", "ownership": "shared", "usageCount": 3},
        ],
        "operations": [],
        "dependencies": [],
        "runtime": {
            "jobConfigPath": "job/VMware-PNET.conf",
            "jobConfigDigest": "a" * 64,
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


class MemoryStore:
    def __init__(self):
        self.operations = {}
        self.by_key = {}
        self.records = {}
        self.events = []

    def load_retirement_operation(self, idempotency_key):
        op_id = self.by_key.get(str(idempotency_key))
        return self.operations.get(op_id)

    def create_retirement_operation(self, intent):
        row = {
            "id": intent["id"],
            "intent": deepcopy(intent),
            "result": {"jobName": intent["jobName"], "readiness": "prepared"},
        }
        self.operations[row["id"]] = row
        self.by_key[intent["idempotencyKey"]] = row["id"]
        self.events.append(("operation_created", intent["jobName"]))
        return row

    def save_retirement_record(self, operation_id, record):
        saved = deepcopy(record)
        self.records[saved["jobName"]] = saved
        self.events.append(("retirement_record_saved", saved["jobName"]))
        return saved

    def finalize_retirement_operation(self, operation_id, state, result):
        row = self.operations[operation_id]
        row["result"] = deepcopy(result)
        row["result"]["state"] = state
        self.events.append(("operation_finalized", state))
        record = self.records.get(row["intent"]["jobName"])
        if record:
            record["state"] = state
            record["retiredAt"] = result["retirementRecord"].get("retiredAt")
        return row

    def load_retirement_record(self, job_name):
        return deepcopy(self.records.get(job_name))


class TempExecutor:
    def __init__(self, tmp_path, proof, *, fail_readback=False, fail_restore=False):
        self.job_path = tmp_path / "job" / "VMware-PNET.conf"
        self.fileset = tmp_path / "fileset" / "VMware-PNET.conf"
        self.pool = tmp_path / "pool" / "PNET.conf"
        self.storage = tmp_path / "storage" / "repo-primary.conf"
        self.schedule = tmp_path / "schedule" / "BC-Policy-PNET.conf"
        for path in (self.job_path, self.fileset, self.pool, self.storage, self.schedule):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.job_path.write_text('Job { Name = "VMware-PNET" }\n', encoding="utf-8")
        self.fileset.write_text("FileSet preserved\n", encoding="utf-8")
        self.pool.write_text("Pool preserved\n", encoding="utf-8")
        self.storage.write_text("Storage preserved\n", encoding="utf-8")
        self.schedule.write_text("Schedule preserved\n", encoding="utf-8")
        self.fail_readback = fail_readback
        self.fail_restore = fail_restore
        self.readback_calls = 0
        self.events = []
        proof["runtime"]["jobConfigPath"] = str(self.job_path)
        proof["runtime"]["jobConfigDigest"] = self._digest(self.job_path.read_text(encoding="utf-8"))

    @staticmethod
    def _digest(text):
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def capture_job_config(self, job_name):
        self.events.append(("capture", job_name))
        text = self.job_path.read_text(encoding="utf-8")
        return {"path": str(self.job_path), "digest": self._digest(text), "content": text, "exists": True}

    def delete_job_config(self, job_name, *, expected_path, expected_digest):
        self.events.append(("delete", job_name))
        assert str(self.job_path) == expected_path
        assert self.capture_job_config(job_name)["digest"] == expected_digest
        self.job_path.unlink()
        return {"removed": True, "path": expected_path}

    def read_job_config(self, job_name):
        self.events.append(("readback", job_name))
        self.readback_calls += 1
        if self.fail_readback and self.readback_calls == 1:
            return {"exists": True, "path": str(self.job_path), "digest": None}
        if not self.job_path.exists():
            return {"exists": False, "path": str(self.job_path), "digest": None}
        text = self.job_path.read_text(encoding="utf-8")
        return {"exists": True, "path": str(self.job_path), "digest": self._digest(text)}

    def restore_job_config(self, beforeimage):
        self.events.append(("restore", beforeimage["path"]))
        if self.fail_restore:
            return {"restored": False}
        Path(beforeimage["path"]).write_text(beforeimage["content"], encoding="utf-8")
        return {"restored": True}


def test_review_blocks_active_dependency_and_shared_job_file():
    result = review_retirement(
        _proof(
            resources=[{"resourceType": "job", "resourceName": "VMware-PNET", "ownership": "shared", "usageCount": 2}],
            operations=[{"kind": "restore", "state": "Running"}],
            dependencies=[{"relation": "required_by", "jobName": "VMware-Child"}],
        )
    )
    codes = {item["code"] for item in result["blockers"]}
    assert {"shared_job_file", "unresolved_operation", "dependency_blocker", "incomplete_proof"} <= codes


def test_execute_persists_record_before_delete_and_preserves_other_resources(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof)
    review = review_retirement(proof)
    result = execute_retirement(
        store,
        executor,
        proof,
        actor="admin",
        idempotency_key=str(uuid4()),
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )
    assert result["readiness"] == "applied"
    assert store.events[:2] == [("operation_created", "VMware-PNET"), ("retirement_record_saved", "VMware-PNET")]
    assert ("delete", "VMware-PNET") in executor.events
    assert not executor.job_path.exists()
    assert executor.fileset.read_text(encoding="utf-8") == "FileSet preserved\n"
    assert executor.pool.read_text(encoding="utf-8") == "Pool preserved\n"
    assert executor.storage.read_text(encoding="utf-8") == "Storage preserved\n"
    assert executor.schedule.read_text(encoding="utf-8") == "Schedule preserved\n"
    assert store.records["VMware-PNET"]["configurationRevisionId"] == "cfg-0001"
    assert store.records["VMware-PNET"]["stableId"] == "managed.pnet"


def test_replay_and_foreign_intent_checks(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof)
    review = review_retirement(proof)
    key = str(uuid4())
    first = execute_retirement(store, executor, proof, actor="admin", idempotency_key=key, review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])
    second = execute_retirement(store, executor, proof, actor="admin", idempotency_key=key, review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])
    assert first["retirementRecord"]["operationId"] == second["retirementRecord"]["operationId"]
    with pytest.raises(ValueError, match="another retirement intent"):
        execute_retirement(store, executor, proof, actor="other", idempotency_key=key, review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])


def test_stale_review_and_drift_are_rejected(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof)
    review = review_retirement(proof)
    with pytest.raises(ValueError, match="drifted since review"):
        execute_retirement(store, executor, proof, actor="admin", idempotency_key=str(uuid4()), review_digest=review["reviewDigest"], proof_revision=8)
    proof["runtime"]["jobConfigDigest"] = "b" * 64
    with pytest.raises(ValueError, match="drifted since review"):
        execute_retirement(store, executor, proof, actor="admin", idempotency_key=str(uuid4()), review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])


def test_failed_readback_rolls_back_original_job_file(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof, fail_readback=True)
    review = review_retirement(proof)
    result = execute_retirement(
        store,
        executor,
        proof,
        actor="admin",
        idempotency_key=str(uuid4()),
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )
    assert result["readiness"] == "failed"
    assert executor.job_path.exists()
    assert store.records["VMware-PNET"]["state"] == "Failed"


def test_unknown_no_resend_when_rollback_cannot_be_confirmed(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof, fail_readback=True, fail_restore=True)
    review = review_retirement(proof)
    key = str(uuid4())
    first = execute_retirement(store, executor, proof, actor="admin", idempotency_key=key, review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])
    second = execute_retirement(store, executor, proof, actor="admin", idempotency_key=key, review_digest=review["reviewDigest"], proof_revision=review["proofRevision"])
    assert first["readiness"] == "unknown"
    assert second["retirementRecord"]["operationId"] == first["retirementRecord"]["operationId"]
    assert store.records["VMware-PNET"]["state"] == "Unknown"


def test_retired_job_discovery_preserves_recovery_refs_without_media_claim(tmp_path):
    proof = _proof()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, proof)
    review = review_retirement(proof)
    execute_retirement(
        store,
        executor,
        proof,
        actor="admin",
        idempotency_key=str(uuid4()),
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )
    result = retired_job_discovery(store, "VMware-PNET")
    assert result["stableId"] == "managed.pnet"
    assert result["retainedRecovery"]["latestJobIds"] == [23, 24]
    assert result["retainedRecovery"]["mediaReadableVerified"] is False
    assert any("Retention and cleanup" in item for item in result["retainedObligations"])
