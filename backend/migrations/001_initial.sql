CREATE SCHEMA IF NOT EXISTS backupcenter;
REVOKE ALL ON SCHEMA backupcenter FROM PUBLIC;
CREATE TABLE backupcenter.schema_migrations (
  version text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backupcenter.connections (
  id uuid PRIMARY KEY,
  name text NOT NULL,
  provider text NOT NULL CHECK (provider = 'bareos'),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backupcenter.workloads (
  id uuid PRIMARY KEY,
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  job_name text NOT NULL,
  display_name text NOT NULL,
  proxy_name text NOT NULL,
  folder_path text NOT NULL,
  identity_source text NOT NULL DEFAULT 'bareos-fileset',
  inventory_id text,
  configured boolean NOT NULL DEFAULT true,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (connection_id, job_name)
);
CREATE TABLE backupcenter.session_observations (
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  job_id bigint NOT NULL,
  payload jsonb NOT NULL,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (connection_id, job_id)
);
CREATE TABLE backupcenter.latest_snapshots (
  connection_id uuid PRIMARY KEY REFERENCES backupcenter.connections(id),
  payload jsonb NOT NULL,
  synced_at timestamptz NOT NULL,
  persisted_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backupcenter.audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  connection_id uuid REFERENCES backupcenter.connections(id),
  actor text NOT NULL,
  event_type text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_created ON backupcenter.audit_events(created_at DESC);
CREATE INDEX workload_connection ON backupcenter.workloads(connection_id);
CREATE TABLE backupcenter.operation_requests (
  id uuid PRIMARY KEY,
  connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
  idempotency_key uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('run', 'cancel', 'restore', 'provision')),
  target text NOT NULL,
  state text NOT NULL CHECK (state IN ('Prepared','Dispatching','Accepted','Running','Completed','Failed','Unknown')),
  actor text NOT NULL,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  job_id bigint,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (connection_id, idempotency_key)
);
