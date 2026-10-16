from copy import deepcopy
from datetime import datetime, timedelta, timezone

from backend.lifecycle_clone import review_clone_candidate
from backend.lifecycle_collectors import ProductionLifecycleCollectors
from backend.lifecycle_retirement import review_retirement


def _now(minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _managed_row(job_name="VMware-PNET", instance_uuid="11111111-1111-1111-1111-111111111111", vm_id="vm-source", repository_id="repo-PNET", deps=None, issues=None):
    deps = deps or []
    issues = issues or []
    return {
        "jobName": job_name,
        "instanceUuid": instance_uuid,
        "inventoryVmId": vm_id,
        "inventoryConnectionId": "conn-1",
        "inventoryIdentity": "instance-uuid",
        "inventoryMatchCount": 1,
        "vcenterUuid": "vc-1",
        "repositoryId": repository_id,
        "storageName": repository_id,
        "filesetName": job_name,
        "poolName": job_name.removeprefix("VMware-"),
        "scheduleName": "VMwareTwiceMonthly",
        "jobDefsName": "DefaultJob",
        "jobConfigPath": f"/etc/bareos/bareos-dir.d/job/{job_name}.conf",
        "jobConfigDigest": "a" * 64,
        "filesetConfigPath": f"/etc/bareos/bareos-dir.d/fileset/{job_name}.conf",
        "filesetConfigDigest": "b" * 64,
        "poolConfigPath": f"/etc/bareos/bareos-dir.d/pool/{job_name}.conf",
        "poolConfigDigest": "c" * 64,
        "storageConfigPath": f"/etc/bareos/bareos-dir.d/storage/{repository_id}.conf",
        "storageConfigDigest": "d" * 64,
        "scheduleConfigPath": "/etc/bareos/bareos-dir.d/schedule/VMwareTwiceMonthly.conf",
        "scheduleConfigDigest": "e" * 64,
        "jobDefsConfigPath": "/etc/bareos/bareos-dir.d/jobdefs/DefaultJob.conf",
        "jobDefsConfigDigest": "f" * 64,
        "resourceUse": {
            "job": {"usageCount": 1, "owners": [job_name], "accounted": True},
            "fileset": {"usageCount": 1, "owners": [job_name], "accounted": True},
            "pool": {"usageCount": 1, "owners": [job_name], "accounted": True},
            "storage": {"usageCount": 1, "owners": [job_name], "accounted": True},
            "jobdefs": {"usageCount": 12, "owners": [job_name], "accounted": True},
            "schedule": {"usageCount": 7, "owners": [job_name], "accounted": True},
        },
        "resourceIssues": issues,
        "dependencies": deps,
        "lifecycleState": "enabled",
        "configDigest": "1" * 64,
        "provenance": {"directorName": "bareos-dir", "directorVersion": "25.1.1", "inventoryServer": "vc.local"},
        "selectorProvenance": {
            "addressing": "uuid",
            "selector": {"uuid": instance_uuid, "vmname": None, "folder": None, "dc": None},
            "selectorCount": 1,
            "matchCount": 1,
            "matchedInventory": {
                "id": vm_id,
                "name": job_name.removeprefix("VMware-"),
                "folder": "/Discovered virtual machine",
                "datacenter": "DC",
                "instanceUuid": instance_uuid,
                "identityQuality": "instance-uuid",
            },
        },
        "sourceCoverage": {"director": True, "inventory": True, "config": True},
    }


def _native_config(job_names, repositories=None):
    repositories = repositories or ["repo-PNET", "repo-CLONE", "repo-ARCHIVE"]
    loaded_jobs = {
        name: {
            "name": name,
            "type": "Backup",
            "fileset": name,
            "pool": name.removeprefix("VMware-"),
            "storage": [repositories[0]],
            "schedule": "VMwareTwiceMonthly",
            "jobdefs": "DefaultJob",
        }
        for name in job_names
    }
    loaded_filesets = {name: {"name": name, "selectors": []} for name in job_names}
    loaded_pools = {name.removeprefix("VMware-"): {"name": name.removeprefix("VMware-")} for name in job_names}
    loaded_storages = {name: {"name": name} for name in repositories}
    return {
        "state": "connected",
        "collectedAt": _now(),
        "loaded": {
            "jobs": loaded_jobs,
            "filesets": loaded_filesets,
            "jobdefs": {"DefaultJob": {"name": "DefaultJob"}},
            "pools": loaded_pools,
            "storages": loaded_storages,
        },
        "coverage": {
            "complete": True,
            "duplicates": {"jobs": [], "filesets": [], "pools": [], "storages": [], "schedules": [], "jobdefs": []},
        },
    }


def _bundle(*, observed=None, native_config=None, inventory=None, monitoring=None):
    job_names = [
        "VMware-PNET",
        "VMware-APP01",
        "VMware-APP02",
        "VMware-APP03",
        "VMware-APP04",
        "VMware-APP05",
        "VMware-APP06",
        "BackupCatalog",
        "InstallSmokeTest",
        "VerifyPool",
        "CatalogMaintenance",
        "PruneFiles",
    ]
    observed = observed or {
        "observedAt": _now(),
        "collectorBlockers": [],
        "director": {"state": "connected", "directorName": "bareos-dir", "version": "25.1.1"},
        "inventory": {"state": "connected", "connectionId": "conn-1", "vcenterUuid": "vc-1", "syncedAt": _now()},
        "config": {"state": "connected", "collectedAt": _now(), "jobCount": 12, "managedJobCount": 7},
        "coverage": {"director": {"complete": True}, "inventory": {"complete": True}, "config": {"complete": True}},
        "jobs": [_managed_row()],
    }
    native_config = native_config or _native_config(job_names)
    inventory = inventory or {
        "state": "connected",
        "connectionId": "conn-1",
        "vcenterUuid": "vc-1",
        "vms": [
            {"id": "vm-source", "instanceUuid": "11111111-1111-1111-1111-111111111111", "name": "PNET", "folder": "/Discovered virtual machine", "datacenter": "DC", "visible": True, "identityQuality": "instance-uuid"},
            {"id": "vm-clone", "instanceUuid": "22222222-2222-2222-2222-222222222222", "name": "PNET-CLONE", "folder": "/Discovered virtual machine", "datacenter": "DC", "visible": True, "identityQuality": "instance-uuid"},
        ],
    }
    monitoring = monitoring or {"connection": "connected", "sessions": [{"name": "VMware-PNET", "type": "Backup", "status": "Succeeded", "sourceJobId": 23}, {"name": "VMware-PNET", "type": "Backup", "status": "Warning", "sourceJobId": 24}]}
    return {"observed": observed, "nativeConfig": native_config, "inventory": inventory, "monitoringSnapshot": monitoring}


class FakeStore:
    configured = True
    connection_id = "conn-1"

    def __init__(self, monitoring=None, operations=None):
        self._monitoring = monitoring
        self._operations = operations or []

    def load(self):
        return deepcopy(self._monitoring)

    def lifecycle_operations(self, job_name):
        return deepcopy(self._operations)


class FakeRegistry:
    def __init__(self, *, entries=None, retired=None, assignment=None, proof=None):
        self._entries = entries or [
            {
                "stable_id": "stable-pnet",
                "instance_uuid": "11111111-1111-1111-1111-111111111111",
                "job_name": "VMware-PNET",
            }
        ]
        self._retired = retired or []
        self._assignment = assignment or {
            "inventory_vm_id": "vm-source",
            "configuration_revision_id": "cfg-1",
            "instance_uuid": "11111111-1111-1111-1111-111111111111",
            "policy_revision": 7,
            "job_name": "VMware-PNET",
            "fileset_name": "VMware-PNET",
            "pool_name": "PNET",
            "storage_name": "repo-PNET",
            "state": "Registered",
        }
        self._proof = proof or {
            "jobName": "VMware-PNET",
            "stableId": "stable-pnet",
            "instanceUuid": "11111111-1111-1111-1111-111111111111",
            "inventoryVmId": "vm-source",
            "inventoryConnectionId": "conn-1",
            "vcenterUuid": "vc-1",
            "repositoryId": "repo-PNET",
            "storageName": "repo-PNET",
            "filesetName": "VMware-PNET",
            "poolName": "PNET",
            "scheduleName": "VMwareTwiceMonthly",
            "jobDefsName": "DefaultJob",
            "dependencies": [],
            "resourceUse": deepcopy(_managed_row()["resourceUse"]),
            "configPaths": {
                "jobConfigPath": "/etc/bareos/bareos-dir.d/job/VMware-PNET.conf",
                "filesetConfigPath": "/etc/bareos/bareos-dir.d/fileset/VMware-PNET.conf",
                "poolConfigPath": "/etc/bareos/bareos-dir.d/pool/PNET.conf",
                "storageConfigPath": "/etc/bareos/bareos-dir.d/storage/repo-PNET.conf",
                "scheduleConfigPath": "/etc/bareos/bareos-dir.d/schedule/VMwareTwiceMonthly.conf",
                "jobDefsConfigPath": "/etc/bareos/bareos-dir.d/jobdefs/DefaultJob.conf",
            },
            "configDigests": {
                "jobConfigDigest": "a" * 64,
                "filesetConfigDigest": "b" * 64,
                "poolConfigDigest": "c" * 64,
                "storageConfigDigest": "d" * 64,
                "scheduleConfigDigest": "e" * 64,
                "jobDefsConfigDigest": "f" * 64,
            },
            "sourceCoverage": {"director": True, "inventory": True, "config": True},
            "provenance": {"directorName": "bareos-dir"},
        }

    def assignment_detail(self, job_name):
        return deepcopy(self._assignment) if job_name == "VMware-PNET" else None

    def enumerate_entries(self):
        return deepcopy(self._entries)

    def proof_snapshot(self, job_name):
        return deepcopy(self._proof) if job_name == "VMware-PNET" else None

    def read_retired_assignments(self):
        return deepcopy(self._retired)


def _collectors(bundle, *, store=None, registry=None, retention=None):
    return ProductionLifecycleCollectors(
        store=store or FakeStore(monitoring=bundle["monitoringSnapshot"]),
        registry=registry or FakeRegistry(),
        source_bundle_provider=lambda: deepcopy(bundle),
        retention_provider=retention,
    )


def test_collect_clone_review_composes_authoritative_sources():
    bundle = _bundle()
    collected = _collectors(bundle).collect_clone_review(
        "VMware-PNET",
        "VMware-CLONE",
        "22222222-2222-2222-2222-222222222222",
        "repo-CLONE",
        "Admin",
    )
    review = review_clone_candidate(
        collected["snapshot"],
        "VMware-PNET",
        new_job_name="VMware-CLONE",
        new_vm_uuid="22222222-2222-2222-2222-222222222222",
        target_repository_id="repo-CLONE",
        trusted_role="Admin",
        registry_evidence=collected["registryEvidence"],
        copy_secrets=False,
    )
    assert review["readiness"] == "candidate_ready"
    assert len(collected["registryEvidence"]["existing_job_names"]) == 12
    assert collected["duplicateProtection"]["targetVm"]["matchCount"] == 1


def test_collect_clone_review_blocks_stale_authenticated_sources():
    bundle = _bundle(observed={**_bundle()["observed"], "observedAt": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()})
    collected = _collectors(bundle).collect_clone_review(
        "VMware-PNET",
        "VMware-CLONE",
        "22222222-2222-2222-2222-222222222222",
        "repo-CLONE",
        "Admin",
    )
    review = review_clone_candidate(
        collected["snapshot"],
        "VMware-PNET",
        new_job_name="VMware-CLONE",
        new_vm_uuid="22222222-2222-2222-2222-222222222222",
        target_repository_id="repo-CLONE",
        trusted_role="Admin",
        registry_evidence=collected["registryEvidence"],
        copy_secrets=False,
    )
    assert review["readiness"] == "blocked"
    assert any("stale" in item.lower() for item in collected["unsupportedChanges"])


def test_collect_clone_review_reports_duplicate_target_vm_assignment():
    bundle = _bundle()
    registry = FakeRegistry(
        entries=[
            {"stable_id": "stable-pnet", "instance_uuid": "11111111-1111-1111-1111-111111111111", "job_name": "VMware-PNET"},
            {"stable_id": "stable-other", "instance_uuid": "22222222-2222-2222-2222-222222222222", "job_name": "VMware-APP01"},
        ]
    )
    collected = _collectors(bundle, registry=registry).collect_clone_review(
        "VMware-PNET",
        "VMware-CLONE",
        "22222222-2222-2222-2222-222222222222",
        "repo-CLONE",
        "Admin",
    )
    review = review_clone_candidate(
        collected["snapshot"],
        "VMware-PNET",
        new_job_name="VMware-CLONE",
        new_vm_uuid="22222222-2222-2222-2222-222222222222",
        target_repository_id="repo-CLONE",
        trusted_role="Admin",
        registry_evidence=collected["registryEvidence"],
        copy_secrets=False,
    )
    assert review["readiness"] == "blocked"
    assert any(item["code"] == "duplicate_assignment" for item in review["blockers"])


def test_collect_retirement_proof_surfaces_runtime_unknown_operations():
    bundle = _bundle(monitoring={"connection": "connected", "sessions": [{"name": "VMware-PNET", "type": "Restore", "status": "unknown", "sourceJobId": 77}]})
    store = FakeStore(monitoring=bundle["monitoringSnapshot"], operations=[{"id": "op-1", "kind": "provision", "state": "Unknown", "parameters": {"summary": "Lifecycle result unknown"}}])
    retention = lambda job_name, snapshot: {
        "recoveryPointCount": 2,
        "latestJobIds": [23, 24],
        "catalogReferenceIds": ["catalog:23", "catalog:24"],
        "catalogVisibilityConfirmed": True,
        "stableRecoveryReferencesConfirmed": True,
        "retentionOwnerConfirmed": True,
        "cleanupOwnerConfirmed": True,
        "mediaReadableVerified": False,
    }
    proof = _collectors(bundle, store=store, retention=retention).collect_retirement_proof("VMware-PNET", "Admin")
    review = review_retirement(proof)
    assert any(item["state"] == "unknown" for item in proof["operations"])
    assert any(item["code"] == "unresolved_operation" for item in review["blockers"])


def test_collect_retirement_proof_blocks_partial_dependencies():
    observed = _bundle()["observed"]
    observed["jobs"] = [_managed_row(deps=[{"relation": "required_by", "jobName": None}])]
    bundle = _bundle(observed=observed)
    retention = lambda job_name, snapshot: {
        "recoveryPointCount": 1,
        "latestJobIds": [23],
        "catalogReferenceIds": ["catalog:23"],
        "catalogVisibilityConfirmed": True,
        "stableRecoveryReferencesConfirmed": True,
        "retentionOwnerConfirmed": True,
        "cleanupOwnerConfirmed": True,
        "mediaReadableVerified": False,
    }
    proof = _collectors(bundle, retention=retention).collect_retirement_proof("VMware-PNET", "Admin")
    review = review_retirement(proof)
    assert proof["runtime"]["hooksVerified"] is False
    assert "unknown-dependency" in proof["runtime"]["hookReferences"]
    assert any(item["code"] == "hook_blocker" for item in review["blockers"])


def test_collect_clone_review_treats_released_staging_as_filtered_when_registry_returns_none():
    bundle = _bundle()
    collected = _collectors(bundle, registry=FakeRegistry(retired=[])).collect_clone_review(
        "VMware-PNET",
        "VMware-CLONE",
        "22222222-2222-2222-2222-222222222222",
        "repo-CLONE",
        "Admin",
    )
    assert collected["duplicateProtection"]["releasedStagingFiltered"] is True
    assert not any("retired" in item["summary"].lower() for item in collected["registryEvidence"]["unresolved_intents"])


def test_collect_retirement_proof_missing_catalog_keeps_recovery_blocked():
    bundle = _bundle(monitoring={"connection": "connected", "sessions": []})
    proof = _collectors(bundle).collect_retirement_proof("VMware-PNET", "Admin")
    review = review_retirement(proof)
    assert proof["retainedRecovery"]["catalogVisibilityConfirmed"] is False
    assert proof["retainedRecovery"]["latestJobIds"] == []
    assert any(item["code"] == "incomplete_proof" for item in review["blockers"])
