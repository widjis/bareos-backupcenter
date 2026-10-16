CREATE TABLE backupcenter.lifecycle_operations (
  id uuid PRIMARY KEY,
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  idempotency_key uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('clone', 'remove')),
  action text NOT NULL CHECK (action IN ('clone_job', 'remove_configuration')),
  actor text NOT NULL,
  state text NOT NULL CHECK (state IN ('Prepared', 'Dispatching', 'Applied', 'Failed', 'Unknown')),
  review_digest text NOT NULL,
  proof_revision integer NOT NULL DEFAULT 0,
  intent_binding text NOT NULL,
  job_name text,
  source_job_name text,
  new_job_name text,
  new_vm_uuid text,
  repository_id text,
  intent jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (connection_id, idempotency_key)
);

CREATE INDEX lifecycle_operations_connection_state
  ON backupcenter.lifecycle_operations(connection_id, state, updated_at DESC);

CREATE INDEX lifecycle_operations_connection_job
  ON backupcenter.lifecycle_operations(connection_id, job_name, updated_at DESC);

CREATE INDEX lifecycle_operations_connection_vm
  ON backupcenter.lifecycle_operations(connection_id, new_vm_uuid, updated_at DESC);

CREATE TABLE backupcenter.lifecycle_operation_claims (
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  claim_key text NOT NULL,
  operation_id uuid NOT NULL REFERENCES backupcenter.lifecycle_operations(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (connection_id, claim_key)
);

CREATE INDEX lifecycle_claims_operation
  ON backupcenter.lifecycle_operation_claims(connection_id, operation_id);

CREATE TABLE backupcenter.lifecycle_retirement_records (
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  job_name text NOT NULL,
  operation_id uuid NOT NULL UNIQUE REFERENCES backupcenter.lifecycle_operations(id) ON DELETE CASCADE,
  state text NOT NULL CHECK (state IN ('Dispatching', 'Applied', 'Failed', 'Unknown')),
  stable_id text NOT NULL,
  vm_instance_uuid text NOT NULL,
  repository_id text NOT NULL,
  configuration_revision_id text NOT NULL,
  proof_revision integer NOT NULL,
  job_revision integer NOT NULL,
  stable_vm_revision integer NOT NULL,
  repository_revision integer NOT NULL,
  retained_recovery jsonb NOT NULL,
  retained_obligations jsonb NOT NULL,
  beforeimage_private jsonb NOT NULL,
  beforeimage_ref jsonb NOT NULL,
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (connection_id, job_name)
);

CREATE INDEX lifecycle_retirement_connection_state
  ON backupcenter.lifecycle_retirement_records(connection_id, state, updated_at DESC);

GRANT SELECT,INSERT,UPDATE ON backupcenter.lifecycle_operations,backupcenter.lifecycle_retirement_records TO backupcenter_runtime;
GRANT SELECT,INSERT,DELETE ON backupcenter.lifecycle_operation_claims TO backupcenter_runtime;
