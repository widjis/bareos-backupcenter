CREATE TABLE backupcenter.inventory_snapshots (
 connection_id uuid PRIMARY KEY,
 payload jsonb NOT NULL,
 synced_at timestamptz NOT NULL,
 last_attempt_at timestamptz NOT NULL DEFAULT now(),
 last_error text
);
CREATE TABLE backupcenter.inventory_vms (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.inventory_snapshots(connection_id),
 moref text NOT NULL,
 instance_uuid text,
 payload jsonb NOT NULL,
 visible boolean NOT NULL DEFAULT true,
 first_seen_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,moref)
);
CREATE INDEX inventory_vm_connection ON backupcenter.inventory_vms(connection_id,visible);
GRANT SELECT,INSERT,UPDATE ON backupcenter.inventory_snapshots,backupcenter.inventory_vms TO backupcenter_runtime;
