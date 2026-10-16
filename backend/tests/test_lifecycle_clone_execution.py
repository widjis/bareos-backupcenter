from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from backend.lifecycle_clone import apply_clone_candidate, review_clone_candidate

SOURCE_VM = "11111111-1111-1111-1111-111111111111"
TARGET_VM = "22222222-2222-2222-2222-222222222222"


def _snapshot(**overrides):
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


def _registry(**overrides):
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
        "resources": [
            {"resource_type": "job", "resource_name": "VMware-PNET", "ownership": "exclusive", "usage_count": 1, "proof_revision": 7}
        ],
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


class MemoryStore:
    def __init__(self, *, fail_commit_numbers: tuple[int, ...] = ()):
        self.intents = {}
        self.rolled_back = False
        self.commit_count = 0
        self.fail_commit_numbers = set(fail_commit_numbers)

    def get_intent(self, intent_id: str):
        row = self.intents.get(intent_id)
        return deepcopy(row) if row else None

    def begin(self):
        return MemoryTx(self)


class MemoryTx:
    def __init__(self, store: MemoryStore):
        self.store = store
        self.pending = deepcopy(store.intents)

    def insert_intent(self, intent_id: str, record: dict):
        if intent_id in self.pending:
            raise ValueError("duplicate intent id")
        self.pending[intent_id] = deepcopy(record)

    def update_intent(self, intent_id: str, record: dict):
        if intent_id not in self.pending:
            raise KeyError(intent_id)
        self.pending[intent_id] = deepcopy(record)

    def read_intent(self, intent_id: str):
        return deepcopy(self.pending[intent_id])

    def commit(self):
        self.store.commit_count += 1
        if self.store.commit_count in self.store.fail_commit_numbers:
            raise RuntimeError("commit failed")
        self.store.intents = self.pending

    def rollback(self):
        self.store.rolled_back = True


class TempExecutor:
    def __init__(self, root: Path, *, state: str = "applied", raise_after_write: bool = False):
        self.root = root
        self.state = state
        self.raise_after_write = raise_after_write
        self.calls = 0

    def apply_clone(self, native_candidate: dict, *, actor: str, intent_id: str):
        self.calls += 1
        target = self.root / intent_id
        target.mkdir(parents=True, exist_ok=True)
        for rel_path, text in native_candidate["resourcePlan"]["files"].items():
            path = target / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if self.raise_after_write:
            raise TimeoutError("post-dispatch timeout")
        if self.state == "unknown":
            return {"state": "unknown", "summary": "Executor reported an unknown outcome; do not resend."}
        return {"state": "applied", "summary": f"Clone files staged locally for {actor}."}


def _review():
    return review_clone_candidate(
        _snapshot(),
        "VMware-PNET",
        new_job_name="VMware-CLONEA",
        new_vm_uuid=TARGET_VM,
        target_repository_id="repo-CLONEA",
        trusted_role="Admin",
        registry_evidence=_registry(),
    )


def test_review_rejects_collision_stale_and_foreign_key_mismatch():
    collision = review_clone_candidate(
        _snapshot(),
        "VMware-PNET",
        new_job_name="VMware-CLONEA",
        new_vm_uuid=TARGET_VM,
        target_repository_id="repo-CLONEA",
        trusted_role="Admin",
        registry_evidence=_registry(existing_job_names=["VMware-PNET", "VMware-CLONEA"]),
    )
    stale = review_clone_candidate(
        _snapshot(),
        "VMware-PNET",
        new_job_name="VMware-CLONEA",
        new_vm_uuid=TARGET_VM,
        target_repository_id="repo-CLONEA",
        trusted_role="Admin",
        registry_evidence=_registry(proof_revision=6),
    )
    mismatch = review_clone_candidate(
        _snapshot(),
        "VMware-PNET",
        new_job_name="VMware-CLONEA",
        new_vm_uuid=TARGET_VM,
        target_repository_id="repo-CLONEA",
        trusted_role="Admin",
        registry_evidence=_registry(source_assignment={**_registry()["source_assignment"], "repository_id": "repo-other"}),
    )
    assert "name_conflict" in {row["code"] for row in collision["blockers"]}
    assert "stale_registry_proof" in {row["code"] for row in stale["blockers"]}
    assert "foreign_key_mismatch" in {row["code"] for row in mismatch["blockers"]}


def test_review_rejects_same_vm_unsupported_repository_and_secret_copy():
    result = review_clone_candidate(
        _snapshot(),
        "VMware-PNET",
        new_job_name="VMware-CLONEB",
        new_vm_uuid=SOURCE_VM,
        target_repository_id="repo-CLONEB",
        trusted_role="Admin",
        registry_evidence=_registry(repositories=[{"id": "repo-CLONEB", "label": "CLONEB", "supported": False}]),
        copy_secrets=True,
    )
    assert {row["code"] for row in result["blockers"]} == {
        "unsupported_repository",
        "same_vm_clone_unsupported",
        "secret_copy_unsupported",
    }


def test_review_builds_disabled_isolated_native_candidate():
    result = _review()
    job_file = result["nativeCandidate"]["resourcePlan"]["files"]["bareos-dir.d/job/CLONEA.conf"]
    fileset_file = result["nativeCandidate"]["resourcePlan"]["files"]["bareos-dir.d/fileset/CLONEA.conf"]
    assert result["readiness"] == "candidate_ready"
    assert result["executionSupported"] is True
    assert " Enabled = no" in job_file
    assert "Schedule =" not in job_file
    assert TARGET_VM in fileset_file and SOURCE_VM not in fileset_file
    assert "VMware-PNET" not in "".join(result["nativeCandidate"]["resourcePlan"]["files"].values())
    assert result["nativeCandidate"]["historyCopied"] is False
    assert result["nativeCandidate"]["secretsCopied"] is False
    assert result["reviewDigest"] == result["reviewDigest"]
    assert result["nativeCandidate"]["candidateDigest"]


def test_apply_commits_temp_resources_and_is_idempotent(tmp_path: Path):
    review = _review()
    store = MemoryStore()
    executor = TempExecutor(tmp_path)
    first = apply_clone_candidate(review, actor="admin@example", intent_id="clone-1", expected_digest=review["reviewDigest"], store=store, executor=executor)
    second = apply_clone_candidate(review, actor="admin@example", intent_id="clone-1", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert first["readiness"] == "completed"
    assert second["readiness"] == "completed"
    assert executor.calls == 1
    assert (tmp_path / "clone-1" / "bareos-dir.d" / "job" / "CLONEA.conf").exists()


def test_unknown_outcome_is_durable_and_not_resent(tmp_path: Path):
    review = _review()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, state="unknown")
    first = apply_clone_candidate(review, actor="admin@example", intent_id="clone-unknown", expected_digest=review["reviewDigest"], store=store, executor=executor)
    second = apply_clone_candidate(review, actor="admin@example", intent_id="clone-unknown", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert first["readiness"] == "unknown"
    assert second["readiness"] == "unknown"
    assert executor.calls == 1
    assert store.intents["clone-unknown"]["state"] == "Unknown"


def test_executor_exception_after_external_write_persists_unknown_and_replay_does_not_resend(tmp_path: Path):
    review = _review()
    store = MemoryStore()
    executor = TempExecutor(tmp_path, raise_after_write=True)
    first = apply_clone_candidate(review, actor="admin@example", intent_id="clone-timeout", expected_digest=review["reviewDigest"], store=store, executor=executor)
    second = apply_clone_candidate(review, actor="admin@example", intent_id="clone-timeout", expected_digest=review["reviewDigest"], store=store, executor=TempExecutor(tmp_path))
    assert first["readiness"] == "unknown"
    assert second["readiness"] == "unknown"
    assert executor.calls == 1
    assert store.intents["clone-timeout"]["state"] == "Unknown"
    assert (tmp_path / "clone-timeout" / "bareos-dir.d" / "job" / "CLONEA.conf").exists()


def test_finalize_commit_failure_leaves_durable_dispatching_and_replay_does_not_resend(tmp_path: Path):
    review = _review()
    store = MemoryStore(fail_commit_numbers=(2,))
    executor = TempExecutor(tmp_path)
    result = apply_clone_candidate(review, actor="admin@example", intent_id="clone-dispatching", expected_digest=review["reviewDigest"], store=store, executor=executor)
    replay = apply_clone_candidate(review, actor="admin@example", intent_id="clone-dispatching", expected_digest=review["reviewDigest"], store=store, executor=TempExecutor(tmp_path))
    assert result["readiness"] == "dispatching"
    assert replay["readiness"] == "dispatching"
    assert executor.calls == 1
    assert store.intents["clone-dispatching"]["state"] == "Dispatching"
    assert "Do not resend" in replay["summary"]


def test_claim_failure_blocks_before_external_execution(tmp_path: Path):
    review = _review()
    store = MemoryStore(fail_commit_numbers=(1,))
    executor = TempExecutor(tmp_path)
    result = apply_clone_candidate(review, actor="admin@example", intent_id="clone-claim-fail", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert result["blockers"] == [{"code": "claim_failed", "summary": "Clone apply could not persist a durable dispatch claim."}]
    assert executor.calls == 0
    assert store.rolled_back is True
    assert store.intents == {}


def test_existing_intent_rejects_foreign_actor_binding(tmp_path: Path):
    review = _review()
    store = MemoryStore()
    executor = TempExecutor(tmp_path)
    apply_clone_candidate(review, actor="admin@example", intent_id="clone-actor", expected_digest=review["reviewDigest"], store=store, executor=executor)
    blocked = apply_clone_candidate(review, actor="other@example", intent_id="clone-actor", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert blocked["blockers"] == [{"code": "idempotency_conflict", "summary": "This intent id is already bound to another actor, action, source, digest or target."}]


def test_digest_mismatch_is_blocked_before_dispatch(tmp_path: Path):
    review = _review()
    tampered = deepcopy(review)
    tampered["nativeCandidate"]["resourcePlan"]["folder"] = "/tmp/tampered"
    store = MemoryStore()
    executor = TempExecutor(tmp_path)
    blocked = apply_clone_candidate(tampered, actor="admin@example", intent_id="clone-digest", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert blocked["blockers"] == [{"code": "review_digest_mismatch", "summary": "Clone apply requires a fresh approved review digest bound to the exact native candidate."}]
    assert executor.calls == 0


def test_crash_after_committed_claim_replay_returns_dispatching_without_second_call(tmp_path: Path):
    review = _review()
    store = MemoryStore()
    store.intents["clone-crash"] = {
        "intentId": "clone-crash",
        "actor": "admin@example",
        "action": review["action"],
        "sourceJobName": review["sourceJobName"],
        "newJobName": review["newJobName"],
        "newVmUuid": review["newVmUuid"],
        "selectedRepositoryId": review["selectedRepositoryId"],
        "reviewDigest": review["reviewDigest"],
        "intentBinding": "seed",
        "state": "Dispatching",
        "response": {
            **review,
            "readiness": "dispatching",
            "executionSupported": False,
            "summary": "Clone dispatch claim is durable. Do not resend while this intent remains unresolved.",
            "executorState": "dispatching",
            "intentId": "clone-crash",
        },
    }
    store.intents["clone-crash"]["intentBinding"] = hashlib.sha256(
        json.dumps(
            {
                "actor": "admin@example",
                "action": review["action"],
                "sourceJobName": review["sourceJobName"],
                "newJobName": review["newJobName"],
                "newVmUuid": review["newVmUuid"],
                "selectedRepositoryId": review["selectedRepositoryId"],
                "reviewDigest": review["reviewDigest"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    executor = TempExecutor(tmp_path)
    result = apply_clone_candidate(review, actor="admin@example", intent_id="clone-crash", expected_digest=review["reviewDigest"], store=store, executor=executor)
    assert result["readiness"] == "dispatching"
    assert executor.calls == 0
