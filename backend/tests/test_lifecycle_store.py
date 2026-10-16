from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from backend.lifecycle_clone import apply_clone_candidate, review_clone_candidate
from backend.lifecycle_retirement import execute_retirement, review_retirement
from backend.lifecycle_store import AlreadyClaimed, LifecycleStore

SOURCE_VM = "11111111-1111-1111-1111-111111111111"
TARGET_VM = "22222222-2222-2222-2222-222222222222"


def _clone_snapshot(**overrides):
    data = {
        "actor_role": "Admin",
        "stable_id": "managed.pnet",
        "job_name": "VMware-PNET",
        "selection_revision": 7,
        "snapshot_revision": 7,
        "identity_revision": 3,
        "managed_vm_ids": [SOURCE_VM],
        "repository_id": "repo-primary",
    }
    data.update(overrides)
    return data


def _clone_registry(**overrides):
    data = {
        "proof_revision": 7,
        "proof_coverage": [
            "operations",
            "dependencies",
            "intents",
            "resources",
            "names",
            "assignments",
            "target_vm",
            "target_repository",
        ],
        "existing_job_names": ["VMware-PNET"],
        "existing_assignments": [],
        "resources": [{"resource_type": "job", "resource_name": "VMware-PNET", "ownership": "exclusive", "usage_count": 1, "proof_revision": 7}],
        "operations": [],
        "dependencies": [],
        "unresolved_intents": [],
        "repositories": [{"id": "repo-CLONEA", "label": "CLONEA", "supported": True}],
        "source_assignment": {
            "stable_id": "managed.pnet",
            "job_name": "VMware-PNET",
            "vm_identity": SOURCE_VM,
            "repository_id": "repo-primary",
        },
    }
    data.update(overrides)
    return data


def _clone_review(**overrides):
    params = {
        "snapshot": _clone_snapshot(),
        "source_job_name": "VMware-PNET",
        "new_job_name": "VMware-CLONEA",
        "new_vm_uuid": TARGET_VM,
        "target_repository_id": "repo-CLONEA",
        "trusted_role": "Admin",
        "registry_evidence": _clone_registry(),
    }
    params.update(overrides)
    return review_clone_candidate(
        params["snapshot"],
        params["source_job_name"],
        new_job_name=params["new_job_name"],
        new_vm_uuid=params["new_vm_uuid"],
        target_repository_id=params["target_repository_id"],
        trusted_role=params["trusted_role"],
        registry_evidence=params["registry_evidence"],
    )


def _retirement_proof(**overrides):
    data = {
        "jobName": "VMware-PNET",
        "stableId": "managed.pnet",
        "vmInstanceUuid": SOURCE_VM,
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


class FakeDatabase:
    def __init__(self):
        self.state = {
            "connections": set(),
            "operations": {},
            "claims": {},
            "retirement_records": {},
            "audit_events": [],
        }
        self.clock = 0
        self.commit_count = 0
        self.log: list[str] = []

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db: FakeDatabase):
        self.db = db
        self.working = deepcopy(db.state)
        self.closed = False

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        self.db.commit_count += 1
        self.db.log.append(f"commit:{self.db.commit_count}")
        self.db.state = deepcopy(self.working)

    def rollback(self):
        self.db.log.append("rollback")
        self.working = deepcopy(self.db.state)

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, conn: FakeConnection):
        self.conn = conn
        self._rows = []

    def execute_tag(self, tag: str, params: tuple):
        method = getattr(self, f"_tag_{tag.replace('.', '_')}")
        method(*params)

    def fetchone(self):
        return deepcopy(self._rows[0]) if self._rows else None

    def fetchall(self):
        return deepcopy(self._rows)

    def close(self):
        return None

    def _next_clock(self):
        self.conn.db.clock += 1
        return self.conn.db.clock

    def _find_operation(self, connection_id: str, *, op_id: str | None = None, key: str | None = None):
        visible = deepcopy(self.conn.db.state["operations"])
        visible.update(deepcopy(self.conn.working["operations"]))
        rows = []
        for row in visible.values():
            if row["connection_id"] != connection_id:
                continue
            if op_id is not None and row["id"] == op_id:
                rows.append(row)
            elif key is not None and row["idempotency_key"] == key:
                rows.append(row)
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return rows

    def _claims_view(self):
        visible = deepcopy(self.conn.db.state["claims"])
        visible.update(deepcopy(self.conn.working["claims"]))
        return visible

    def _tag_lifecycle_ensure_connection(self, connection_id: str):
        self.conn.working["connections"].add(connection_id)
        self._rows = []

    def _tag_lifecycle_lock(self, key: str):
        self.conn.db.log.append(f"lock:{key}")
        self._rows = []

    def _tag_lifecycle_select_operation_by_key(self, connection_id: str, key: str):
        self._rows = self._find_operation(connection_id, key=key)

    def _tag_lifecycle_select_operation_by_id(self, connection_id: str, op_id: str):
        self._rows = self._find_operation(connection_id, op_id=op_id)

    def _tag_lifecycle_select_operation_by_id_or_key(self, connection_id: str, op_id: str, key: str):
        rows = self._find_operation(connection_id, op_id=op_id)
        if not rows:
            rows = self._find_operation(connection_id, key=key)
        self._rows = rows

    def _tag_lifecycle_select_claim(self, connection_id: str, claim_key: str):
        op_id = self._claims_view().get((connection_id, claim_key))
        if not op_id:
            self._rows = []
            return
        row = deepcopy(self.conn.db.state["operations"].get((connection_id, op_id)) or self.conn.working["operations"][(connection_id, op_id)])
        self._rows = [{"claim_key": claim_key, "idempotency_key": row["idempotency_key"]}]

    def _tag_lifecycle_insert_operation(self, *params):
        if len(params) == 16:
            (
                op_id,
                connection_id,
                key,
                action,
                actor,
                state,
                review_digest,
                proof_revision,
                intent_binding,
                job_name,
                source_job_name,
                new_job_name,
                new_vm_uuid,
                repository_id,
                intent,
                result,
            ) = params
            kind = "clone"
        else:
            (
                op_id,
                connection_id,
                key,
                actor,
                review_digest,
                proof_revision,
                intent_binding,
                job_name,
                intent,
                result,
            ) = params
            kind = "remove"
            action = "remove_configuration"
            state = "Prepared"
            source_job_name = None
            new_job_name = None
            new_vm_uuid = None
            repository_id = None
        row = {
            "id": op_id,
            "connection_id": connection_id,
            "idempotency_key": key,
            "kind": kind,
            "action": action,
            "actor": actor,
            "state": state,
            "review_digest": review_digest,
            "proof_revision": proof_revision,
            "intent_binding": intent_binding,
            "job_name": job_name,
            "source_job_name": source_job_name,
            "new_job_name": new_job_name,
            "new_vm_uuid": new_vm_uuid,
            "repository_id": repository_id,
            "intent": deepcopy(intent),
            "result": deepcopy(result),
            "created_at": self._next_clock(),
            "updated_at": self.conn.db.clock,
        }
        self.conn.working["operations"][(connection_id, op_id)] = row
        self._rows = [row]

    def _tag_lifecycle_insert_claim(self, connection_id: str, claim_key: str, operation_id: str):
        key = (connection_id, claim_key)
        if key in self.conn.working["claims"]:
            raise ValueError("duplicate claim")
        self.conn.working["claims"][key] = operation_id
        self._rows = []

    def _tag_lifecycle_insert_audit(self, connection_id: str, actor: str, event_type: str, details: dict):
        self.conn.working["audit_events"].append(
            {
                "connection_id": connection_id,
                "actor": actor,
                "event_type": event_type,
                "details": deepcopy(details),
            }
        )
        self._rows = []

    def _tag_lifecycle_update_operation(self, *params):
        if len(params) == 4:
            state, result, connection_id, operation_id = params
        else:
            result, connection_id, operation_id = params
            state = "Dispatching"
        row = self.conn.working["operations"][(connection_id, operation_id)]
        row["state"] = state
        row["result"] = deepcopy(result)
        row["updated_at"] = self._next_clock()
        self._rows = [row]

    def _tag_lifecycle_delete_claims(self, connection_id: str, operation_id: str):
        self.conn.working["claims"] = {
            key: value for key, value in self.conn.working["claims"].items() if not (key[0] == connection_id and value == operation_id)
        }
        self._rows = []

    def _tag_lifecycle_upsert_retirement_record(
        self,
        connection_id: str,
        job_name: str,
        operation_id: str,
        stable_id: str,
        vm_instance_uuid: str,
        repository_id: str,
        configuration_revision_id: str,
        proof_revision: int,
        job_revision: int,
        stable_vm_revision: int,
        repository_revision: int,
        retained_recovery: dict,
        retained_obligations: list,
        beforeimage_private: dict,
        beforeimage_ref: dict,
    ):
        row = {
            "connection_id": connection_id,
            "job_name": job_name,
            "operation_id": operation_id,
            "state": "Dispatching",
            "stable_id": stable_id,
            "vm_instance_uuid": vm_instance_uuid,
            "repository_id": repository_id,
            "configuration_revision_id": configuration_revision_id,
            "proof_revision": proof_revision,
            "job_revision": job_revision,
            "stable_vm_revision": stable_vm_revision,
            "repository_revision": repository_revision,
            "retained_recovery": deepcopy(retained_recovery),
            "retained_obligations": list(retained_obligations),
            "beforeimage_private": deepcopy(beforeimage_private),
            "beforeimage_ref": deepcopy(beforeimage_ref),
            "retired_at": None,
            "created_at": self._next_clock(),
            "updated_at": self.conn.db.clock,
        }
        self.conn.working["retirement_records"][(connection_id, job_name)] = row
        self._rows = [row]

    def _tag_lifecycle_update_retirement_record(self, state: str, retired_at: str | None, connection_id: str, operation_id: str):
        for key, row in self.conn.working["retirement_records"].items():
            if key[0] == connection_id and row["operation_id"] == operation_id:
                row["state"] = state
                row["retired_at"] = retired_at
                row["updated_at"] = self._next_clock()
                break
        self._rows = []

    def _tag_lifecycle_select_retirement_record(self, connection_id: str, job_name: str):
        row = self.conn.working["retirement_records"].get((connection_id, job_name))
        if not row:
            self._rows = []
            return
        op = self.conn.working["operations"][(connection_id, row["operation_id"])]
        self._rows = [{**deepcopy(row), "operation_state": op["state"], "operation_result": deepcopy(op["result"])}]


class FakeBaseStore:
    def __init__(self, db: FakeDatabase, connection_id: str):
        self.connection_id = connection_id
        self._db = db
        self.allowed_calls = []

    def connect(self):
        return self._db.connect()

    def actor_allowed(self, username, kind="run"):
        self.allowed_calls.append((username, kind))
        return username != "revoked"


class CloneExecutor:
    def __init__(self, db: FakeDatabase, *, state: str = "applied"):
        self.db = db
        self.state = state
        self.calls = 0

    def apply_clone(self, native_candidate: dict, *, actor: str, intent_id: str):
        self.calls += 1
        self.db.log.append(f"executor:{self.calls}:commit_count={self.db.commit_count}")
        return {"state": self.state, "summary": f"executor {self.state} for {actor}"}


class RetirementExecutor:
    def __init__(self, db: FakeDatabase, tmp_path: Path, proof: dict, *, fail_readback=False, fail_restore=False, durable_handle=True):
        self.db = db
        self.job_path = tmp_path / "job" / "VMware-PNET.conf"
        self.job_path.parent.mkdir(parents=True, exist_ok=True)
        self.job_path.write_text('Job { Name = "VMware-PNET" Password = "secret" }\n', encoding="utf-8")
        proof["runtime"]["jobConfigPath"] = str(self.job_path)
        proof["runtime"]["jobConfigDigest"] = self._digest(self.job_path.read_text(encoding="utf-8"))
        self.fail_readback = fail_readback
        self.fail_restore = fail_restore
        self.durable_handle = durable_handle
        self.delete_calls = 0

    @staticmethod
    def _digest(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def capture_job_config(self, job_name: str):
        text = self.job_path.read_text(encoding="utf-8")
        payload = {
            "path": str(self.job_path),
            "digest": self._digest(text),
            "content": text,
            "exists": True,
        }
        if self.durable_handle:
            payload["receiptId"] = f"capture:{job_name}"
        return payload

    def delete_job_config(self, job_name: str, *, expected_path: str, expected_digest: str):
        self.delete_calls += 1
        self.db.log.append(f"delete:{self.db.commit_count}")
        assert expected_path == str(self.job_path)
        assert expected_digest == self.capture_job_config(job_name)["digest"]
        self.job_path.unlink()
        return {"removed": True, "path": expected_path}

    def read_job_config(self, job_name: str):
        if self.fail_readback:
            return {"exists": True, "path": str(self.job_path), "digest": None}
        if not self.job_path.exists():
            return {"exists": False, "path": str(self.job_path), "digest": None}
        text = self.job_path.read_text(encoding="utf-8")
        return {"exists": True, "path": str(self.job_path), "digest": self._digest(text)}

    def restore_job_config(self, beforeimage: dict):
        if self.fail_restore:
            return {"restored": False}
        Path(beforeimage["path"]).write_text(beforeimage["content"], encoding="utf-8")
        return {"restored": True}


def test_clone_commit_order_and_cross_connection_reads():
    db = FakeDatabase()
    store_a = LifecycleStore(FakeBaseStore(db, "conn-a"))
    store_b = LifecycleStore(FakeBaseStore(db, "conn-b"))
    review = _clone_review()
    executor = CloneExecutor(db)

    result = apply_clone_candidate(
        review,
        actor="admin@example",
        intent_id="00000000-0000-0000-0000-000000000111",
        expected_digest=review["reviewDigest"],
        store=store_a,
        executor=executor,
    )

    assert result["readiness"] == "completed"
    timeline = [item for item in db.log if item.startswith("commit:") or item.startswith("executor:")]
    assert timeline[:3] == ["commit:1", "executor:1:commit_count=1", "commit:2"]
    assert store_a.get_intent("00000000-0000-0000-0000-000000000111")["state"] == "Applied"
    assert store_b.get_intent("00000000-0000-0000-0000-000000000111") is None


def test_clone_actor_binding_and_concurrent_target_claim_are_blocked():
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    review = _clone_review()
    unknown = apply_clone_candidate(
        review,
        actor="admin@example",
        intent_id="00000000-0000-0000-0000-000000000211",
        expected_digest=review["reviewDigest"],
        store=store,
        executor=CloneExecutor(db, state="unknown"),
    )
    assert unknown["readiness"] == "unknown"

    foreign = apply_clone_candidate(
        review,
        actor="other@example",
        intent_id="00000000-0000-0000-0000-000000000211",
        expected_digest=review["reviewDigest"],
        store=store,
        executor=CloneExecutor(db),
    )
    assert foreign["blockers"][0]["code"] == "idempotency_conflict"

    blocked = apply_clone_candidate(
        review,
        actor="admin@example",
        intent_id="00000000-0000-0000-0000-000000000212",
        expected_digest=review["reviewDigest"],
        store=store,
        executor=CloneExecutor(db),
    )
    assert blocked["blockers"][0]["code"] == "claim_failed"
    assert store.get_intent("00000000-0000-0000-0000-000000000212") is None


def test_clone_same_key_second_claim_raises_after_stale_initial_miss():
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    review = _clone_review()
    key = "00000000-0000-0000-0000-000000000311"
    assert store.get_intent(key) is None
    first = store.begin()
    first.insert_intent(
        key,
        {
            "intentId": key,
            "actor": "admin@example",
            "action": review["action"],
            "sourceJobName": review["sourceJobName"],
            "newJobName": review["newJobName"],
            "newVmUuid": review["newVmUuid"],
            "selectedRepositoryId": review["selectedRepositoryId"],
            "reviewDigest": review["reviewDigest"],
            "intentBinding": "binding-1",
            "state": "Dispatching",
            "response": {"jobName": review["jobName"], "summary": "dispatching"},
        },
    )
    second = store.begin()
    first.commit()
    with pytest.raises(AlreadyClaimed, match="already durably claimed"):
        second.insert_intent(
            key,
            {
                "intentId": key,
                "actor": "admin@example",
                "action": review["action"],
                "sourceJobName": review["sourceJobName"],
                "newJobName": review["newJobName"],
                "newVmUuid": review["newVmUuid"],
                "selectedRepositoryId": review["selectedRepositoryId"],
                "reviewDigest": review["reviewDigest"],
                "intentBinding": "binding-1",
                "state": "Dispatching",
                "response": {"jobName": review["jobName"], "summary": "dispatching"},
            },
        )
    second.rollback()
    assert store.get_intent(key)["state"] == "Dispatching"
    lock_keys = [item for item in db.log if item.startswith("lock:")]
    assert lock_keys[-4:] == sorted(lock_keys[-4:])


def test_retirement_persists_beforeimage_before_delete_and_unknown_is_retained(tmp_path: Path):
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    proof = _retirement_proof()
    executor = RetirementExecutor(db, tmp_path, proof, fail_readback=True, fail_restore=True)
    review = review_retirement(proof)
    key = str(uuid4())

    first = execute_retirement(
        store,
        executor,
        proof,
        actor="admin",
        idempotency_key=key,
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )
    second = execute_retirement(
        store,
        executor,
        proof,
        actor="admin",
        idempotency_key=key,
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )

    assert first["readiness"] == "unknown"
    assert second["retirementRecord"]["operationId"] == first["retirementRecord"]["operationId"]
    timeline = [item for item in db.log if item.startswith("commit:") or item.startswith("delete:")]
    assert timeline[:3] == ["commit:1", "commit:2", "delete:2"]
    assert executor.delete_calls == 1
    record = store.load_retirement_record("VMware-PNET")
    assert record["state"] == "Unknown"
    assert "content" not in str(record["beforeImageReference"])


def test_retirement_same_key_second_claim_raises_and_no_second_delete(tmp_path: Path):
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    proof = _retirement_proof()
    executor = RetirementExecutor(db, tmp_path, proof)
    review = review_retirement(proof)
    key = str(uuid4())

    assert store.load_retirement_operation(key) is None
    first = store.create_retirement_operation(
        {
            "id": str(uuid4()),
            "actor": "admin",
            "idempotencyKey": key,
            "jobName": proof["jobName"],
            "reviewDigest": review["reviewDigest"],
            "proofRevision": review["proofRevision"],
        }
    )
    with pytest.raises(AlreadyClaimed, match="already durably claimed"):
        store.create_retirement_operation(
            {
                "id": str(uuid4()),
                "actor": "admin",
                "idempotencyKey": key,
                "jobName": proof["jobName"],
                "reviewDigest": review["reviewDigest"],
                "proofRevision": review["proofRevision"],
            }
        )
    assert first["state"] == "Prepared"
    assert executor.delete_calls == 0


def test_retirement_beforeimage_requires_opaque_handle_before_delete(tmp_path: Path):
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    proof = _retirement_proof()
    executor = RetirementExecutor(db, tmp_path, proof, durable_handle=False)
    review = review_retirement(proof)

    with pytest.raises(ValueError, match="opaque helper receipt or handle"):
        execute_retirement(
            store,
            executor,
            proof,
            actor="admin",
            idempotency_key=str(uuid4()),
            review_digest=review["reviewDigest"],
            proof_revision=review["proofRevision"],
        )
    assert executor.delete_calls == 0


def test_retirement_finalize_uses_terminal_cas_and_keeps_unknown_claim():
    db = FakeDatabase()
    store = LifecycleStore(FakeBaseStore(db, "conn-a"))
    operation = store.create_retirement_operation(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "actor": "admin",
            "idempotencyKey": "22222222-2222-2222-2222-222222222222",
            "jobName": "VMware-PNET",
            "reviewDigest": "digest-1",
            "proofRevision": 7,
        }
    )
    store.save_retirement_record(
        operation["id"],
        {
            "jobName": "VMware-PNET",
            "stableId": "managed.pnet",
            "vmInstanceUuid": SOURCE_VM,
            "repositoryId": "repo-primary",
            "configurationRevisionId": "cfg-0001",
            "proofRevision": 7,
            "jobRevision": 41,
            "stableVmRevision": 12,
            "repositoryRevision": 9,
            "beforeImage": {"path": "/etc/bareos/job.conf", "digest": "a" * 64, "content": "secret=yes", "exists": True, "receiptId": "helper-1"},
            "retainedRecovery": {"recoveryPointCount": 1, "latestJobIds": [1], "catalogReferenceIds": ["catalog:1"], "mediaReadableVerified": False},
            "retainedObligations": ["Retention remains explicit."],
        },
    )
    store.finalize_retirement_operation(
        operation["id"],
        "Unknown",
        {"jobName": "VMware-PNET", "summary": "unknown", "retirementRecord": {"retiredAt": None}},
    )
    final = store.finalize_retirement_operation(
        operation["id"],
        "Applied",
        {"jobName": "VMware-PNET", "summary": "should-not-overwrite", "retirementRecord": {"retiredAt": "2026-10-16T12:00:00Z"}},
    )
    assert final["state"] == "Unknown"
    with pytest.raises(AlreadyClaimed, match="unresolved lifecycle operation"):
        store.create_retirement_operation(
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "actor": "admin",
                "idempotencyKey": "44444444-4444-4444-4444-444444444444",
                "jobName": "VMware-PNET",
                "reviewDigest": "digest-2",
                "proofRevision": 7,
            }
        )


def test_retired_lookup_is_sanitized_and_connection_scoped(tmp_path: Path):
    db = FakeDatabase()
    store_a = LifecycleStore(FakeBaseStore(db, "conn-a"))
    store_b = LifecycleStore(FakeBaseStore(db, "conn-b"))
    proof = _retirement_proof()
    executor = RetirementExecutor(db, tmp_path, proof)
    review = review_retirement(proof)

    result = execute_retirement(
        store_a,
        executor,
        proof,
        actor="admin",
        idempotency_key=str(uuid4()),
        review_digest=review["reviewDigest"],
        proof_revision=review["proofRevision"],
    )

    assert result["readiness"] == "applied"
    lookup = store_a.load_retirement_record("VMware-PNET")
    assert lookup["state"] == "Applied"
    assert lookup["beforeImageReference"]["receiptId"] == "capture:VMware-PNET"
    assert "content" not in str(lookup)
    assert store_b.load_retirement_record("VMware-PNET") is None


def test_native_opaque_beforeimage_is_preserved_without_content():
    from backend.lifecycle_store import _sanitize_beforeimage
    private, reference = _sanitize_beforeimage({"path": "/etc/bareos/job/PNET.conf", "digest": "a" * 64, "exists": True, "opaqueRef": "/var/lib/bareos-lifecycle-resources/capture.json"})
    assert reference["opaqueRef"].endswith("capture.json")
    assert "content" not in reference and "opaqueRef" not in private
