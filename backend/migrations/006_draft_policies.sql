CREATE TABLE backupcenter.protection_policies (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 name text NOT NULL,
 owner text NOT NULL REFERENCES backupcenter.app_users(username),
 revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 state text NOT NULL DEFAULT 'Draft' CHECK(state IN ('Draft','Applied','Retired')),
 definition jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,name)
);
GRANT SELECT,INSERT,UPDATE ON backupcenter.protection_policies TO backupcenter_runtime;
