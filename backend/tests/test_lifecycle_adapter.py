from copy import deepcopy
from uuid import UUID

from backend.lifecycle_adapter import build_disable_preview

VM_ID = UUID("11111111-1111-1111-1111-111111111111")


def _snapshot(**overrides):
    data = {
        "actor_role": "Admin",
        "stable_id": "managed.pnet",
        "job_name": "Managed PNET",
        "selection_revision": 7,
        "snapshot_revision": 7,
        "identity_revision": 3,
        "managed_vm_ids": [VM_ID],
        "repository_id": "repo-primary",
    }
    data.update(overrides)
    return data


def _registry(**overrides):
    data = {
        "proof_revision": 7,
        "proof_coverage": ["operations", "dependencies", "intents", "resources"],
        "resources": [
            {
                "resource_type": "schedule",
                "resource_name": "managed-pnet.schedule",
                "ownership": "exclusive",
                "usage_count": 1,
                "proof_revision": 9,
            }
        ],
        "operations": [],
        "dependencies": [],
        "unresolved_intents": [],
    }
    data.update(overrides)
    return data


def test_missing_job_fails_closed():
    result = build_disable_preview(_snapshot(job_name="Other Job"), "Managed PNET", trusted_role="Admin", registry_evidence=_registry())
    assert result["blockers"] == [{"code": "job_not_found", "summary": "Server snapshot does not prove managed job Managed PNET."}]


def test_source_error_is_exposed_without_planner_call():
    result = build_disable_preview(_snapshot(source_error="director_unavailable"), "Managed PNET", trusted_role="Admin", registry_evidence=_registry())
    assert result["blockers"] == [{"code": "source_unavailable", "summary": "Snapshot source is unavailable; raw diagnostics are withheld."}]


def test_stale_and_partial_snapshot_fail_closed():
    stale = build_disable_preview(_snapshot(selection_revision=6), "Managed PNET", trusted_role="Admin", registry_evidence=_registry())
    partial = build_disable_preview(
        {k: v for k, v in _snapshot().items() if k != "repository_id"},
        "Managed PNET",
        trusted_role="Admin",
        registry_evidence=_registry(),
    )
    assert stale["blockers"][0]["code"] == "stale_snapshot"
    assert partial["blockers"][0]["code"] == "partial_snapshot"


def test_missing_registry_proof_is_explicit():
    result = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin")
    assert result["blockers"] == [{"code": "missing_registry_proof", "summary": "Registry evidence is required for disable preview."}]
    assert result["executionSupported"] is False


def test_forged_snapshot_role_cannot_elevate_trusted_role():
    result = build_disable_preview(_snapshot(actor_role="Admin"), "Managed PNET", trusted_role="Viewer", registry_evidence=_registry())
    assert {row["code"] for row in result["blockers"]} == {"permission_denied"}


def test_deterministic_digest_uses_canonical_payload():
    registry_a = _registry()
    registry_b = deepcopy(registry_a)
    registry_b["proof_coverage"] = ["resources", "intents", "dependencies", "operations"]
    first = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin", registry_evidence=registry_a)
    second = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin", registry_evidence=registry_b)
    assert first["digest"] == second["digest"]


def test_fully_proven_fixture_maps_to_read_only_disable_preview():
    result = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin", registry_evidence=_registry())
    assert result["jobName"] == "Managed PNET"
    assert result["action"] == "disable_schedule"
    assert result["executionSupported"] is False
    assert result["blockers"] == []
    assert {row["code"] for row in result["impacts"]} == {
        "schedule_disabled",
        "backups_preserved",
        "active_sessions_unchanged",
    }


def test_incomplete_registry_coverage_and_missing_schedule_binding_do_not_default_safe():
    result = build_disable_preview(
        _snapshot(),
        "Managed PNET",
        trusted_role="Admin",
        registry_evidence=_registry(proof_coverage=["operations"], resources=[]),
    )
    assert {row["code"] for row in result["blockers"]} == {
        "missing_registry_proof",
        "missing_resource_bindings",
    }


def test_missing_explicit_registry_lists_are_not_assumed_empty():
    registry = _registry()
    del registry["operations"]
    result = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin", registry_evidence=registry)
    assert result["blockers"][0]["code"] == "missing_registry_proof"


def test_malformed_evidence_is_blocked_without_exception_or_raw_diagnostics():
    registry = _registry(proof_coverage=[{}])
    result = build_disable_preview(_snapshot(), "Managed PNET", trusted_role="Admin", registry_evidence=registry)
    assert result["blockers"][0]["code"] == "invalid_registry_evidence"
    result = build_disable_preview(_snapshot(managed_vm_ids=["invalid"]), "Managed PNET", trusted_role="Admin", registry_evidence=_registry())
    assert result["blockers"][0]["code"] == "invalid_evidence"
    result = build_disable_preview(_snapshot(source_error="password=private"), "Managed PNET", trusted_role="Admin")
    assert "private" not in str(result)
