CREATE TABLE backupcenter.app_users (
 username text PRIMARY KEY,
 password_hash text NOT NULL,
 role text NOT NULL CHECK(role IN ('Admin','Backup Operator','Viewer')),
 enabled boolean NOT NULL DEFAULT true,
 failures integer NOT NULL DEFAULT 0,
 locked_until timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backupcenter.app_sessions (
 token_hash text PRIMARY KEY,
 username text NOT NULL REFERENCES backupcenter.app_users(username),
 expires_at timestamptz NOT NULL,
 revoked boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX app_session_username ON backupcenter.app_sessions(username);
GRANT SELECT,INSERT,UPDATE ON backupcenter.app_users,backupcenter.app_sessions TO backupcenter_runtime;
