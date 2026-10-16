from copy import deepcopy

from backend.lifecycle_adapter import build_disable_preview
from backend.lifecycle_proof import normalize_disable_evidence


VM_UUID = "11111111-1111-1111-1111-111111111111"


def fixture():
    return {
        "trusted_role": "Admin",
        "collector": {"complete": True, "revision": 7},
        "exact_job": {
            "stable_id": "managed.pnet",
            "job_name": "Managed PNET",
            "selection_revision": 7,
            "snapshot_revision": 7,
            "identity_revision": 3,
            "repository_id": "repo-primary",
            "managed_vm_uuid": VM_UUID,
            "schedule": {
                "resource_name": "managed-pnet.schedule",
                "ownership": "exclusive",
                "usage_count": 1,
                "proof_revision": 7,
            },
        },
        "registry": {
            "revision": 7,
            "job_name": "Managed PNET",
            "stable_id": "managed.pnet",
            "repository_id": "repo-primary",
            "coverage": ["dependencies", "intents", "operations", "resources"],
            "enumerated": {
                "operations": True,
                "dependencies": True,
                "intents": True,
                "resources": True,
            },
            "operations": [],
            "dependencies": [],
            "unresolved_intents": [],
            "resources": [
                {
                    "resource_type": "schedule",
                    "resource_name": "managed-pnet.schedule",
                    "ownership": "exclusive",
                    "usage_count": 1,
                    "proof_revision": 7,
                }
            ],
        },
    }


def test_complete_fixture_normalizes_and_is_accepted_by_adapter():
    normalized = normalize_disable_evidence(fixture(), "Managed PNET")
    assert "blockers" not in normalized
    result = build_disable_preview(
        normalized["snapshot"],
        "Managed PNET",
        trusted_role=normalized["trusted_role"],
        registry_evidence=normalized["registry_evidence"],
    )
    assert result["action"] == "disable_schedule"
    assert result["executionSupported"] is False
    assert not result["blockers"]


def test_absent_or_stale_proof_is_blocked():
    missing = normalize_disable_evidence({"trusted_role": "Admin"}, "Managed PNET")
    assert {row["code"] for row in missing["blockers"]} >= {"missing_collector_proof", "missing_exact_job", "missing_registry_proof"}
    stale = fixture()
    stale["registry"]["revision"] = 6
    blocked = normalize_disable_evidence(stale, "Managed PNET")
    assert {row["code"] for row in blocked["blockers"]} >= {"stale_registry_proof"}


def test_same_job_cross_repository_mismatch_is_blocked():
    evidence = fixture()
    evidence["registry"]["repository_id"] = "repo-other"
    blocked = normalize_disable_evidence(evidence, "Managed PNET")
    assert {row["code"] for row in blocked["blockers"]} == {"cross_repository_mismatch"}


def test_dependency_and_active_operations_remain_blockers_through_adapter():
    evidence = fixture()
    evidence["registry"]["operations"] = [
        {"operation_id": "op-1", "kind": "backup", "state": "active", "summary": "running"}
    ]
    evidence["registry"]["dependencies"] = [
        {"relation": "required_by", "related_stable_id": "managed.child", "related_job_name": "Managed Child", "proof_revision": 7}
    ]
    normalized = normalize_disable_evidence(evidence, "Managed PNET")
    result = build_disable_preview(
        normalized["snapshot"],
        "Managed PNET",
        trusted_role=normalized["trusted_role"],
        registry_evidence=normalized["registry_evidence"],
    )
    assert {row["code"] for row in result["blockers"]} >= {"pending_operation", "dependency_blocker"}


def test_proof_digest_changes_for_full_relevant_evidence_beyond_display_caps():
    evidence = fixture()
    many = deepcopy(evidence)
    many["registry"]["operations"] = [
        {"operation_id": f"op-{n}", "kind": "other", "state": "completed", "summary": f"summary {n}"}
        for n in range(40)
    ]
    changed = deepcopy(many)
    changed["registry"]["operations"][-1]["summary"] = "tail changed"
    assert normalize_disable_evidence(many, "Managed PNET")["proof_digest"] != normalize_disable_evidence(changed, "Managed PNET")["proof_digest"]


def test_registry_schedule_binding_is_never_fabricated():
    evidence=fixture();evidence["registry"]["resources"]=[]
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="missing_resource_proof"

def test_invalid_uuid_is_blocked_before_adapter():
    evidence=fixture();evidence["exact_job"]["managed_vm_uuid"]="invalid"
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="invalid_evidence"

def test_boolean_revision_and_truncated_registry_are_not_complete_proof():
    evidence=fixture();evidence["collector"]["revision"]=True
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="missing_collector_proof"
    evidence=fixture();evidence["registry"]["truncated"]=True
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="partial_registry"

def test_stale_dependency_revision_is_rejected():
    evidence=fixture();evidence["registry"]["dependencies"]=[{"relation":"required_by","related_stable_id":"managed.child","related_job_name":"Managed Child","proof_revision":6}]
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="stale_registry_proof"


def test_boolean_identity_revision_is_not_a_real_revision():
    evidence=fixture();evidence["exact_job"]["identity_revision"]=True
    assert normalize_disable_evidence(evidence,"Managed PNET")["blockers"][0]["code"]=="invalid_revision"
