CREATE TABLE backupcenter.session_alerts (
 id uuid PRIMARY KEY,
 connection_id uuid NOT NULL REFERENCES backupcenter.connections(id),
 job_name text NOT NULL,
 source_job_id bigint NOT NULL CHECK(source_job_id>0),
 severity text NOT NULL CHECK(severity IN ('Error','Warning')),
 state text NOT NULL DEFAULT 'Open' CHECK(state IN ('Open','Acknowledged','Resolved')),
 revision integer NOT NULL DEFAULT 1,
 evidence jsonb NOT NULL,
 acknowledged_by text REFERENCES backupcenter.app_users(username),
 resolved_by_job_id bigint,
 first_seen_at timestamptz NOT NULL DEFAULT now(),
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(connection_id,source_job_id)
);
GRANT SELECT,INSERT,UPDATE ON backupcenter.session_alerts TO backupcenter_runtime;
