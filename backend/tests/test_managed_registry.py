from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.managed_registry import ManagedRegistryRepository, reconcile_managed_registry
from integration.collect_managed_registry import _build_observed


def _recent_iso(minutes_ago: int = 5) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _observed(**overrides):
    job = {
        "jobName": "VMware-PNET",
        "instanceUuid": "11111111-1111-1111-1111-111111111111",
        "inventoryVmId": "22222222-2222-2222-2222-222222222222",
        "inventoryConnectionId": "33333333-3333-3333-3333-333333333333",
        "inventoryIdentity": "instance-uuid",
        "inventoryMatchCount": 1,
        "vcenterUuid": "vc-1",
        "repositoryId": "SMB-PNET",
        "storageName": "SMB-PNET",
        "filesetName": "VMware-PNET",
        "poolName": "PNET",
        "scheduleName": "VMwareTwiceMonthly",
        "jobDefsName": "DefaultJob",
        "jobConfigPath": "/etc/bareos/bareos-dir.d/job/PNET.conf",
        "jobConfigDigest": "a" * 64,
        "filesetConfigPath": "/etc/bareos/bareos-dir.d/fileset/PNET.conf",
        "filesetConfigDigest": "b" * 64,
        "poolConfigPath": "/etc/bareos/bareos-dir.d/pool/PNET.conf",
        "poolConfigDigest": "c" * 64,
        "storageConfigPath": "/etc/bareos/bareos-dir.d/storage/PNET.conf",
        "storageConfigDigest": "d" * 64,
        "scheduleConfigPath": "/etc/bareos/bareos-dir.d/schedule/VMwareTwiceMonthly.conf",
        "scheduleConfigDigest": "e" * 64,
        "jobDefsConfigPath": "/etc/bareos/bareos-dir.d/jobdefs/DefaultJob.conf",
        "jobDefsConfigDigest": "f" * 64,
        "resourceUse": {
            "job": {"usageCount": 1, "owners": ["VMware-PNET"], "accounted": True},
            "fileset": {"usageCount": 1, "owners": ["VMware-PNET"], "accounted": True},
            "pool": {"usageCount": 1, "owners": ["VMware-PNET"], "accounted": True},
            "storage": {"usageCount": 1, "owners": ["VMware-PNET"], "accounted": True},
            "jobdefs": {"usageCount": 3, "owners": ["VMware-PNET", "BackupCatalog", "InstallSmokeTest"], "accounted": True},
            "schedule": {"usageCount": 1, "owners": ["VMware-PNET"], "accounted": True},
        },
        "resourceIssues": [],
        "dependencies": [],
        "lifecycleState": "enabled",
        "configDigest": "1" * 64,
        "provenance": {"directorName": "bareos-dir", "directorVersion": "25.1.1", "inventoryServer": "vc.local"},
        "selectorProvenance": {
            "addressing": "uuid",
            "selector": {"uuid": "11111111-1111-1111-1111-111111111111", "vmname": None, "folder": None, "dc": None},
            "selectorCount": 1,
            "matchCount": 1,
            "matchedInventory": {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "PNET",
                "folder": "/Discovered virtual machine",
                "datacenter": "DC",
                "instanceUuid": "11111111-1111-1111-1111-111111111111",
                "identityQuality": "instance-uuid",
            },
        },
        "sourceCoverage": {"director": True, "inventory": True, "config": True},
    }
    payload = {
        "observedAt": _recent_iso(),
        "collectorBlockers": [],
        "director": {"state": "connected", "directorName": "bareos-dir", "version": "25.1.1"},
        "inventory": {
            "state": "connected",
            "connectionId": "33333333-3333-3333-3333-333333333333",
            "vcenterUuid": "vc-1",
            "syncedAt": _recent_iso(),
        },
        "config": {"state": "connected", "collectedAt": _recent_iso(), "jobCount": 3, "managedJobCount": 1},
        "coverage": {"director": {"complete": True}, "inventory": {"complete": True}, "config": {"complete": True}},
        "jobs": [job],
    }
    payload.update(overrides)
    return payload


def _disk_job(name, fileset, pool, storage, schedule="VMwareTwiceMonthly", jobdefs="DefaultJob", enabled="yes"):
    return {
        "name": name,
        "path": f"/etc/bareos/bareos-dir.d/job/{name[7:]}.conf",
        "digest": f"{name}-disk-job",
        "fileset": fileset,
        "pool": pool,
        "storage": storage,
        "schedule": schedule,
        "jobdefs": jobdefs,
        "enabled": enabled,
        "dependencyTargets": [],
    }


def _collector_inputs(managed_jobs, inventory_rows, *, wrong_loaded_match=False, include_paths=False, observed_at=None, synced_at=None):
    observed_at = observed_at or _recent_iso()
    synced_at = synced_at or _recent_iso()
    loaded_jobs = {}
    disk_jobs = {}
    disk_filesets = {}
    loaded_filesets = {}
    disk_pools = {}
    loaded_pools = {}
    disk_storages = {}
    loaded_storages = {}
    workloads = []
    for job_name, vm_name, folder, dc, storage_name in managed_jobs:
        loaded_jobs[job_name] = {
            "name": job_name,
            "type": "Backup",
            "fileset": job_name,
            "pool": job_name[7:],
            "fullbackuppool": job_name[7:],
            "incrementalbackuppool": job_name[7:],
            "differentialbackuppool": job_name[7:],
            "storage": [storage_name],
            "schedule": "VMwareTwiceMonthly",
            "jobdefs": "DefaultJob",
            "client": "bareos-fd",
            "digest": f"{job_name}-loaded-job",
            "afterJobTargets": [],
        }
        disk_jobs[job_name] = _disk_job(job_name, job_name, job_name[7:], ("WRONG-" + storage_name) if wrong_loaded_match else storage_name)
        disk_filesets[job_name] = {
            "name": job_name,
            "path": f"/etc/bareos/bareos-dir.d/fileset/{job_name[7:]}.conf",
            "digest": f"{job_name}-disk-fileset",
            "selectors": [{"uuid": None, "vmname": vm_name, "folder": folder, "dc": dc}],
            "pluginCount": 1,
            "includePaths": ["/etc/bareos/include/managed-extra.conf"] if include_paths else [],
            "includeAccounted": not include_paths,
        }
        loaded_filesets[job_name] = {
            "name": job_name,
            "selectors": [{"uuid": None, "vmname": vm_name, "folder": folder, "dc": dc}],
            "digest": f"{job_name}-loaded-fileset",
        }
        disk_pools[job_name[7:]] = {"name": job_name[7:], "path": f"/etc/bareos/bareos-dir.d/pool/{job_name[7:]}.conf", "digest": f"{job_name}-disk-pool"}
        loaded_pools[job_name[7:]] = {"name": job_name[7:], "storage": [storage_name], "digest": f"{job_name}-loaded-pool"}
        disk_storages[storage_name] = {"name": storage_name, "path": f"/etc/bareos/bareos-dir.d/storage/{job_name[7:]}.conf", "digest": f"{job_name}-disk-storage"}
        loaded_storages[storage_name] = {"name": storage_name, "device": [storage_name], "digest": f"{job_name}-loaded-storage"}
        workloads.append({"job": job_name, "evidence": "Backup recorded"})
    loaded_jobs["BackupCatalog"] = {
        "name": "BackupCatalog",
        "type": "Backup",
        "fileset": "Catalog",
        "pool": "Incremental",
        "fullbackuppool": "Full",
        "incrementalbackuppool": "Incremental",
        "differentialbackuppool": "Differential",
        "storage": ["File"],
        "schedule": "",
        "jobdefs": "DefaultJob",
        "client": "bareos-fd",
        "digest": "catalog-loaded",
        "afterJobTargets": [],
    }
    loaded_jobs["InstallSmokeTest"] = {
        "name": "InstallSmokeTest",
        "type": "Backup",
        "fileset": "InstallSmokeTest",
        "pool": "Incremental",
        "fullbackuppool": "Full",
        "incrementalbackuppool": "Incremental",
        "differentialbackuppool": "Differential",
        "storage": ["File"],
        "schedule": "",
        "jobdefs": "DefaultJob",
        "client": "bareos-fd",
        "digest": "smoke-loaded",
        "afterJobTargets": [],
    }
    for name in ("Catalog", "InstallSmokeTest"):
        disk_filesets[name] = {
            "name": name,
            "path": f"/etc/bareos/bareos-dir.d/fileset/{name}.conf",
            "digest": f"{name}-disk",
            "selectors": [],
            "pluginCount": 0,
            "includePaths": [],
            "includeAccounted": True,
        }
        loaded_filesets[name] = {"name": name, "selectors": [], "digest": f"{name}-loaded"}
    for name in ("Incremental", "Full", "Differential"):
        disk_pools[name] = {"name": name, "path": f"/etc/bareos/bareos-dir.d/pool/{name}.conf", "digest": f"{name}-disk"}
        loaded_pools[name] = {"name": name, "storage": [], "digest": f"{name}-loaded"}
    disk_storages["File"] = {"name": "File", "path": "/etc/bareos/bareos-dir.d/storage/File.conf", "digest": "file-storage-disk"}
    loaded_storages["File"] = {"name": "File", "device": ["FileStorage"], "digest": "file-storage-loaded"}
    raw = {"director": {"name": "bareos-dir", "version": "25.1.1"}}
    inventory = {
        "state": "connected",
        "connectionId": "33333333-3333-3333-3333-333333333333",
        "vcenterUuid": "vc-1",
        "server": "vc.local",
        "syncedAt": synced_at,
        "vms": inventory_rows,
    }
    config = {
        "state": "connected",
        "collectedAt": observed_at,
        "disk": {
            "jobs": disk_jobs,
            "filesets": disk_filesets,
            "pools": disk_pools,
            "storages": disk_storages,
            "schedules": {"VMwareTwiceMonthly": {"name": "VMwareTwiceMonthly", "path": "/etc/bareos/bareos-dir.d/schedule/VMwareTwiceMonthly.conf", "digest": "schedule-disk"}},
            "jobdefs": {"DefaultJob": {"name": "DefaultJob", "path": "/etc/bareos/bareos-dir.d/jobdefs/DefaultJob.conf", "digest": "jobdefs-disk"}},
        },
        "loaded": {
            "jobs": loaded_jobs,
            "filesets": loaded_filesets,
            "jobdefs": {"DefaultJob": {"name": "DefaultJob", "digest": "jobdefs-loaded"}},
            "pools": loaded_pools,
            "storages": loaded_storages,
        },
        "coverage": {
            "complete": True,
            "duplicates": {"jobs": [], "filesets": [], "pools": [], "storages": [], "schedules": [], "jobdefs": []},
        },
    }
    return raw, inventory, workloads, config


class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rows = []

    def execute(self, sql, params=None):
        sql = " ".join(str(sql).split())
        params = params or ()
        if "FROM backupcenter.protection_assignments pa JOIN backupcenter.configuration_revisions cr" in sql:
            self.rows = [
                {
                    "inventory_vm_id": row["inventory_vm_id"],
                    "instance_uuid": row["instance_uuid"],
                    "configuration_revision_id": row["configuration_revision_id"],
                    "job_name": row["job_name"],
                    "state": row["state"],
                    "revision_state": row["revision_state"],
                    "revision_payload": deepcopy(row["revision_payload"]),
                }
                for row in self.store.retired
            ]
        elif "SELECT inventory_vm_id, configuration_revision_id" in sql:
            row = next((r for r in self.store.entries.values() if r["job_name"] == params[1]), None)
            self.rows = [deepcopy(row)] if row else []
        elif "SELECT stable_id, configuration_revision_id, inventory_vm_id" in sql and "ORDER BY job_name" in sql:
            self.rows = [deepcopy(row) for row in sorted(self.store.entries.values(), key=lambda r: r["job_name"])]
        elif "SELECT proof_snapshot FROM backupcenter.managed_registry_entries" in sql:
            row = next((r for r in self.store.entries.values() if r["job_name"] == params[1]), None)
            self.rows = [{"proof_snapshot": deepcopy(row["proof_snapshot"])}] if row else []
        elif "INSERT INTO backupcenter.connections" in sql:
            self.rows = []
        elif "INSERT INTO backupcenter.managed_registry_receipts" in sql:
            self.store.receipts.append({"id": params[0], "connection_id": params[1], "observed_digest": params[2], "status": params[3], "payload": params[4].adapted})
            self.rows = []
        elif "SELECT iv.id, iv.connection_id, iv.instance_uuid, iv.visible, iv.payload" in sql:
            row = self.store.inventory_rows.get((params[0], params[1]))
            self.rows = [deepcopy(row)] if row else []
        elif "FROM backupcenter.managed_registry_entries WHERE connection_id=%s AND stable_id=%s FOR UPDATE" in sql:
            row = self.store.entries.get(params[1])
            self.rows = [deepcopy(row)] if row else []
        elif "FROM backupcenter.managed_registry_entries WHERE connection_id=%s AND (job_name=%s OR instance_uuid=%s)" in sql:
            rows = [deepcopy(r) for r in self.store.entries.values() if (r["job_name"] == params[1] or r["instance_uuid"] == params[2]) and r["stable_id"] != params[3]]
            self.rows = rows
        elif "UPDATE backupcenter.managed_registry_entries SET" in sql:
            row = self.store.entries[params[17]]
            row.update(
                configuration_revision_id=params[0],
                inventory_vm_id=params[1],
                inventory_connection_id=params[2],
                vcenter_uuid=params[3],
                job_name=params[4],
                repository_id=params[5],
                storage_name=params[6],
                fileset_name=params[7],
                pool_name=params[8],
                schedule_name=params[9],
                jobdefs_name=params[10],
                lifecycle_state=params[11],
                revision=params[12],
                configuration_digest=params[13],
                source_digest=params[14],
                proof_snapshot=params[15].adapted,
                provenance=params[16].adapted,
            )
            self.rows = []
        elif "INSERT INTO backupcenter.managed_registry_entries(" in sql:
            self.store.entries[params[3]] = {
                "id": params[0],
                "connection_id": params[1],
                "configuration_revision_id": params[2],
                "stable_id": params[3],
                "inventory_vm_id": params[4],
                "inventory_connection_id": params[5],
                "instance_uuid": params[6],
                "vcenter_uuid": params[7],
                "job_name": params[8],
                "repository_id": params[9],
                "storage_name": params[10],
                "fileset_name": params[11],
                "pool_name": params[12],
                "schedule_name": params[13],
                "jobdefs_name": params[14],
                "lifecycle_state": params[15],
                "revision": params[16],
                "configuration_digest": params[17],
                "source_digest": params[18],
                "proof_snapshot": params[19].adapted,
                "provenance": params[20].adapted,
            }
            self.rows = []
        else:
            raise AssertionError(f"Unhandled SQL: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self, cursor_factory=None):
        return FakeCursor(self.store)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        return None


class FakeStore:
    def __init__(self):
        self.connection_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        self.entries = {}
        self.retired = []
        self.receipts = []
        self.inventory_rows = {
            (
                "22222222-2222-2222-2222-222222222222",
                "33333333-3333-3333-3333-333333333333",
            ): {
                "id": "22222222-2222-2222-2222-222222222222",
                "connection_id": "33333333-3333-3333-3333-333333333333",
                "instance_uuid": "11111111-1111-1111-1111-111111111111",
                "visible": True,
                "payload": {
                    "name": "PNET",
                    "folder": "/Discovered virtual machine",
                    "datacenter": "DC",
                    "identityQuality": "instance-uuid",
                },
                "snapshot_vcenter_uuid": "vc-1",
            }
        }

    def connect(self):
        return FakeConn(self)


def test_collector_resolves_six_name_folder_datacenter_variants():
    managed_jobs = [
        ("VMware-MTIMRWCNTDEV", "MTIMRWCNTDEV", "/Discovered virtual machine", "DC", "SMB-MTIMRWCNTDEV"),
        ("VMware-MTIMRWKF01", "MTIMRWKF01", "/Production", "DC", "SMB-MTIMRWKF01"),
        ("VMware-MTIMRWNTP01", "MTIMRWNTP01", "/Discovered virtual machine", "DC", "SMB-MTIMRWNTP01"),
        ("VMware-MTIMRWNTP02", "MTIMRWNTP02", "/Discovered virtual machine", "DC", "SMB-MTIMRWNTP02"),
        ("VMware-MTIMRWPGSQL01", "MTIMRWPGSQL01", "/Discovered virtual machine", "DC", "SMB-MTIMRWPGSQL01"),
        ("VMware-MTIMRWZTNA01", "MTIMRWZTNA01", "/Discovered virtual machine", "DC", "SMB-MTIMRWZTNA01"),
    ]
    inventory_rows = [
        {
            "id": str(uuid4()),
            "instanceUuid": f"50000000-0000-0000-0000-{index:012d}",
            "name": vm_name,
            "folder": folder,
            "datacenter": dc,
            "identityQuality": "instance-uuid",
        }
        for index, (_, vm_name, folder, dc, _) in enumerate(managed_jobs, start=1)
    ]
    raw, inventory, workloads, config = _collector_inputs(managed_jobs, inventory_rows)
    observed = _build_observed(raw, inventory, workloads, config, [])
    assert len(observed["jobs"]) == 6
    assert all(row["instanceUuid"] for row in observed["jobs"])
    assert {row["selectorProvenance"]["addressing"] for row in observed["jobs"]} == {"name-folder-datacenter"}


def test_collector_requires_exact_folder_and_datacenter_for_name_resolution():
    managed_jobs = [("VMware-MTIMRWKF01", "MTIMRWKF01", "/Production", "DC", "SMB-MTIMRWKF01")]
    inventory_rows = [
        {
            "id": "vm-correct",
            "instanceUuid": "5009-0000-0000-0000-000000000001",
            "name": "MTIMRWKF01",
            "folder": "/Production",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        },
        {
            "id": "vm-wrong-folder",
            "instanceUuid": "5009-0000-0000-0000-000000000002",
            "name": "MTIMRWKF01",
            "folder": "/Discovered virtual machine",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        },
        {
            "id": "vm-wrong-dc",
            "instanceUuid": "5009-0000-0000-0000-000000000003",
            "name": "MTIMRWKF01",
            "folder": "/Production",
            "datacenter": "OTHER",
            "identityQuality": "instance-uuid",
        },
    ]
    raw, inventory, workloads, config = _collector_inputs(managed_jobs, inventory_rows)
    observed = _build_observed(raw, inventory, workloads, config, [])
    row = observed["jobs"][0]
    assert row["inventoryVmId"] == "vm-correct"
    assert row["selectorProvenance"]["matchCount"] == 1


def test_collector_marks_ambiguous_name_selector_as_unresolved():
    managed_jobs = [("VMware-MTIMRWKF01", "MTIMRWKF01", "/Production", "DC", "SMB-MTIMRWKF01")]
    inventory_rows = [
        {
            "id": "vm-1",
            "instanceUuid": "5009-0000-0000-0000-000000000001",
            "name": "MTIMRWKF01",
            "folder": "/Production",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        },
        {
            "id": "vm-2",
            "instanceUuid": "5009-0000-0000-0000-000000000002",
            "name": "MTIMRWKF01",
            "folder": "/Production",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        },
    ]
    raw, inventory, workloads, config = _collector_inputs(managed_jobs, inventory_rows)
    observed = _build_observed(raw, inventory, workloads, config, [])
    row = observed["jobs"][0]
    assert row["instanceUuid"] is None
    assert row["selectorProvenance"]["matchCount"] == 2


def test_collector_counts_jobdefs_sharing_across_all_loaded_jobs():
    managed_jobs = [("VMware-PNET", "PNET", "/Discovered virtual machine", "DC", "SMB-PNET")]
    inventory_rows = [
        {
            "id": "vm-pnet",
            "instanceUuid": "11111111-1111-1111-1111-111111111111",
            "name": "PNET",
            "folder": "/Discovered virtual machine",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        }
    ]
    raw, inventory, workloads, config = _collector_inputs(managed_jobs, inventory_rows)
    observed = _build_observed(raw, inventory, workloads, config, [])
    assert observed["jobs"][0]["resourceUse"]["jobdefs"]["usageCount"] == 3
    assert set(observed["jobs"][0]["resourceUse"]["jobdefs"]["owners"]) == {"VMware-PNET", "BackupCatalog", "InstallSmokeTest"}


def test_collector_reports_loaded_resource_mismatch_and_include_path_issue():
    managed_jobs = [("VMware-PNET", "PNET", "/Discovered virtual machine", "DC", "SMB-PNET")]
    inventory_rows = [
        {
            "id": "vm-pnet",
            "instanceUuid": "11111111-1111-1111-1111-111111111111",
            "name": "PNET",
            "folder": "/Discovered virtual machine",
            "datacenter": "DC",
            "identityQuality": "instance-uuid",
        }
    ]
    raw, inventory, workloads, config = _collector_inputs(managed_jobs, inventory_rows, wrong_loaded_match=True, include_paths=True)
    observed = _build_observed(raw, inventory, workloads, config, [])
    codes = {item["code"] for item in observed["jobs"][0]["resourceIssues"]}
    assert {"loaded_resource_mismatch", "unknown_include_paths"} <= codes


def test_reconcile_blocks_stale_and_future_source_timestamps():
    observed = _observed(
        observedAt="2024-10-16T12:00:00+00:00",
        inventory={"state": "connected", "connectionId": "33333333-3333-3333-3333-333333333333", "vcenterUuid": "vc-1", "syncedAt": "3026-10-16T12:00:00+00:00"},
    )
    result = reconcile_managed_registry(observed, [])
    codes = {item["code"] for item in result["blockers"]}
    assert {"stale_source", "future_source"} <= codes


def test_reconcile_blocks_missing_uuid_and_partial_resource():
    observed = _observed()
    observed["jobs"][0]["inventoryIdentity"] = "moref-only"
    observed["jobs"][0]["resourceUse"]["fileset"]["accounted"] = False
    result = reconcile_managed_registry(observed, [])
    assert result["status"] == "blocked"
    assert {"missing_uuid", "resource_partial"} <= {item["code"] for item in result["blockers"]}


def test_reconcile_blocks_conflicting_unverified_retired_assignment():
    retired = [{"inventoryVmId": "22222222-2222-2222-2222-222222222222", "instanceUuid": "11111111-1111-1111-1111-111111111111", "configurationRevisionId": str(uuid4()), "jobName": "VMware-PNET", "state": "Retired"}]
    result = reconcile_managed_registry(_observed(), retired)
    assert result["status"] == "blocked"
    assert "conflicting_retired_assignment" in {item["code"] for item in result["blockers"]}


def test_repository_excludes_verified_released_staging_from_retired_rows():
    store = FakeStore()
    store.retired = [
        {
            "inventory_vm_id": "released-vm",
            "instance_uuid": "released-uuid",
            "configuration_revision_id": str(uuid4()),
            "job_name": "VMware-PNET",
            "state": "Retired",
            "revision_state": "Validated",
            "revision_payload": {"liveApplied": True},
        },
        {
            "inventory_vm_id": "blocked-vm",
            "instance_uuid": "blocked-uuid",
            "configuration_revision_id": str(uuid4()),
            "job_name": "VMware-BLOCKED",
            "state": "Retired",
            "revision_state": "Failed",
            "revision_payload": {"liveApplied": True},
        },
    ]
    repo = ManagedRegistryRepository(store)
    rows = repo.read_retired_assignments()
    assert rows == [
        {
            "inventoryVmId": "blocked-vm",
            "instanceUuid": "blocked-uuid",
            "configurationRevisionId": store.retired[1]["configuration_revision_id"],
            "jobName": "VMware-BLOCKED",
            "state": "Retired",
        }
    ]


def test_repository_applies_replays_and_exposes_assignment_detail():
    store = FakeStore()
    repo = ManagedRegistryRepository(store)
    first = repo.reconcile(_observed())
    second = repo.reconcile(_observed())
    assert first["status"] == "Applied"
    assert second["status"] == "Replay"
    detail = repo.assignment_detail("VMware-PNET")
    assert detail["job_name"] == "VMware-PNET"
    assert detail["storage_name"] == "SMB-PNET"
    assert detail["policy_revision"] == 1


def test_repository_requires_authoritative_persisted_inventory():
    store = FakeStore()
    store.inventory_rows = {}
    repo = ManagedRegistryRepository(store)
    with pytest.raises(ValueError, match="authoritative persisted inventory"):
        repo.reconcile(_observed())


def test_repository_revision_cas_rejects_stale_expected_revision():
    store = FakeStore()
    repo = ManagedRegistryRepository(store)
    repo.reconcile(_observed())
    changed = _observed()
    changed["jobs"][0]["storageName"] = "SMB-NEW"
    changed["jobs"][0]["repositoryId"] = "SMB-NEW"
    changed["jobs"][0]["storageConfigPath"] = "/etc/bareos/bareos-dir.d/storage/NEW.conf"
    changed["jobs"][0]["storageConfigDigest"] = "9" * 64
    changed["jobs"][0]["configDigest"] = "8" * 64
    stable_id = next(iter(store.entries))
    with pytest.raises(ValueError, match="revision changed"):
        repo.reconcile(changed, expected_revisions={stable_id: 0})


def test_repository_blocks_job_rename_conflict_for_same_stable_id():
    store = FakeStore()
    repo = ManagedRegistryRepository(store)
    repo.reconcile(_observed())
    renamed = _observed()
    renamed["jobs"][0]["jobName"] = "VMware-RENAMED"
    with pytest.raises(ValueError, match="job rename conflict"):
        repo.reconcile(renamed)


def test_repository_enumeration_and_proof_snapshot():
    store = FakeStore()
    repo = ManagedRegistryRepository(store)
    repo.reconcile(_observed())
    rows = repo.enumerate_entries()
    proof = repo.proof_snapshot("VMware-PNET")
    assert len(rows) == 1
    assert rows[0]["revision"] == 1
    assert proof["jobName"] == "VMware-PNET"
    assert proof["selectorProvenance"]["addressing"] == "uuid"
    assert proof["configPaths"]["jobConfigPath"].endswith("PNET.conf")
