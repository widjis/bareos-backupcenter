from backend.lifecycle_collector import collect_disable_preview


def _snapshot(**overrides):
    data = {
        "connection": "connected",
        "jobs": [
            {"name": "VMware-PNET", "enabled": True, "schedule": "managed-pnet.schedule"},
            {"name": "VMware-OTHER", "enabled": True},
        ],
        "workloads": [{"job": "VMware-PNET", "instanceUuid": "5208e076-eb89-9f06-2ef2-790ac92b4d71"}],
        "sourceErrors": {},
        "persistence": {"state": "connected"},
    }
    data.update(overrides)
    return data


def test_empty_snapshot_and_missing_trusted_role_fail_closed():
    result = collect_disable_preview({}, "VMware-PNET", trusted_role="")
    assert {item["code"] for item in result["blockers"]} == {"missing_trusted_role", "partial_snapshot"}
    assert result["executionSupported"] is False


def test_exact_job_name_is_required():
    result = collect_disable_preview(_snapshot(), "vmware-pnet", trusted_role="Admin")
    assert result["blockers"] == [
        {"code": "job_not_found", "summary": "Current snapshot does not include managed job vmware-pnet by exact name."}
    ]


def test_missing_jobs_list_is_partial_snapshot():
    result = collect_disable_preview({"persistence": {"state": "connected"}}, "VMware-PNET", trusted_role="Admin")
    assert result["blockers"][0]["code"] == "partial_snapshot"


def test_stale_snapshot_and_missing_persistence_are_explicit():
    result = collect_disable_preview(
        _snapshot(connection="stale", persistence={"state": "unavailable"}),
        "VMware-PNET",
        trusted_role="Admin",
    )
    codes = {item["code"] for item in result["blockers"]}
    assert {"stale_snapshot", "missing_persistence_proof", "partial_snapshot"} <= codes


def test_partial_job_sources_are_explicit():
    result = collect_disable_preview(
        _snapshot(connection="partial", sourceErrors={"jobs": "password=secret"}),
        "VMware-PNET",
        trusted_role="Admin",
    )
    codes = {item["code"] for item in result["blockers"]}
    assert {"partial_snapshot", "missing_stable_identity_proof", "missing_resource_proof", "missing_registry_proof"} <= codes
    assert "secret" not in str(result)


def test_current_snapshot_never_fabricates_authoritative_proof():
    result = collect_disable_preview(_snapshot(), "VMware-PNET", trusted_role="Admin")
    codes = {item["code"] for item in result["blockers"]}
    assert {"partial_snapshot", "missing_stable_identity_proof", "missing_resource_proof", "missing_registry_proof"} <= codes
    assert result["impacts"][0]["code"] == "read_only_preview"


def test_snapshot_role_labels_are_not_trusted():
    result = collect_disable_preview(_snapshot(actor_role="Admin"), "VMware-PNET", trusted_role="")
    assert "missing_trusted_role" in {item["code"] for item in result["blockers"]}


def test_output_stays_bounded_and_secret_free():
    result = collect_disable_preview(
        _snapshot(
            jobs=[{"name": f"VMware-{i:03d}", "password": "top-secret"} for i in range(30)] + [{"name": "VMware-PNET"}],
            sourceErrors={"filesets": "vcpass=top-secret"},
        ),
        "VMware-PNET",
        trusted_role="Admin",
    )
    assert len(result["blockers"]) <= 8
    assert len(result["impacts"]) <= 8
    assert "top-secret" not in str(result)
    assert "jobs" not in result and "snapshot" not in result


def test_forged_snapshot_admin_cannot_elevate_trusted_viewer():
    result=collect_disable_preview(_snapshot(actor_role="Admin"),"VMware-PNET",trusted_role="Viewer")
    assert "permission_denied" in {item["code"] for item in result["blockers"]}
    assert result["executionSupported"] is False
