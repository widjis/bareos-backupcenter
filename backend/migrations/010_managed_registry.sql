CREATE TABLE backupcenter.managed_registry_entries (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 configuration_revision_id uuid NOT NULL,
 stable_id uuid NOT NULL,
 inventory_vm_id uuid NOT NULL REFERENCES backupcenter.inventory_vms(id),
 inventory_connection_id uuid NOT NULL REFERENCES backupcenter.inventory_snapshots(connection_id),
 instance_uuid text NOT NULL,
 vcenter_uuid text NOT NULL,
 job_name text NOT NULL,
 repository_id text NOT NULL,
 storage_name text NOT NULL,
 fileset_name text NOT NULL,
 pool_name text NOT NULL,
 schedule_name text,
 jobdefs_name text,
 lifecycle_state text NOT NULL CHECK(lifecycle_state IN ('enabled','disabled','manual_only')),
 revision integer NOT NULL CHECK(revision>=1),
 configuration_digest text NOT NULL,
 source_digest text NOT NULL,
 proof_snapshot jsonb NOT NULL,
 provenance jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id, stable_id),
 UNIQUE(connection_id, job_name),
 UNIQUE(connection_id, inventory_vm_id),
 UNIQUE(connection_id, instance_uuid)
);

CREATE TABLE backupcenter.managed_registry_receipts (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 observed_digest text NOT NULL,
 status text NOT NULL CHECK(status IN ('Applied','Blocked','Replay')),
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX managed_registry_entries_connection_job ON backupcenter.managed_registry_entries(connection_id, job_name);
CREATE INDEX managed_registry_entries_connection_instance ON backupcenter.managed_registry_entries(connection_id, instance_uuid);
CREATE INDEX managed_registry_entries_connection_revision ON backupcenter.managed_registry_entries(connection_id, revision DESC);
CREATE INDEX managed_registry_receipts_connection_created ON backupcenter.managed_registry_receipts(connection_id, created_at DESC);

GRANT SELECT,INSERT,UPDATE ON backupcenter.managed_registry_entries,backupcenter.managed_registry_receipts TO backupcenter_runtime;
