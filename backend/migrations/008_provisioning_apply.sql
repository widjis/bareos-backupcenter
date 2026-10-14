CREATE TABLE backupcenter.configuration_revisions (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 policy_id uuid REFERENCES backupcenter.protection_policies(id),
 policy_revision integer NOT NULL DEFAULT 0 CHECK(policy_revision>=0),
 actor text NOT NULL REFERENCES backupcenter.app_users(username),
 state text NOT NULL CHECK(state IN ('Prepared','Validated','Failed','Retired')),
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backupcenter.protection_assignments (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 inventory_vm_id uuid NOT NULL REFERENCES backupcenter.inventory_vms(id),
 instance_uuid text NOT NULL,
 configuration_revision_id uuid NOT NULL REFERENCES backupcenter.configuration_revisions(id),
 policy_id uuid REFERENCES backupcenter.protection_policies(id),
 policy_revision integer NOT NULL DEFAULT 0 CHECK(policy_revision>=0),
 job_name text NOT NULL,
 fileset_name text NOT NULL,
 pool_name text NOT NULL,
 storage_name text NOT NULL,
 state text NOT NULL CHECK(state IN ('Prepared','Failed','Retired')),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,inventory_vm_id),
 UNIQUE(connection_id,job_name)
);
CREATE INDEX configuration_revision_connection_created ON backupcenter.configuration_revisions(connection_id,created_at DESC);
CREATE INDEX protection_assignment_connection_state ON backupcenter.protection_assignments(connection_id,state,updated_at DESC);
GRANT SELECT,INSERT,UPDATE ON backupcenter.configuration_revisions,backupcenter.protection_assignments TO backupcenter_runtime;
