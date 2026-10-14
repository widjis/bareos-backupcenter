"""Provision the app database through the authorized PostgreSQL host SSH login."""
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from contextlib import closing

import psycopg2
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DATABASE = "backupcenter"
ROLE = "backupcenter_runtime"


def bootstrap():
    env_path = ROOT / ".env"
    values = dotenv_values(env_path)
    parsed = urlparse(values["POSTGRES_HOST"] if "://" in values["POSTGRES_HOST"] else "//" + values["POSTGRES_HOST"])
    local = ROOT / ".local"
    local.mkdir(mode=0o700, exist_ok=True)
    local.chmod(0o700)
    askpass = local / "postgres-askpass"
    askpass.write_text("#!" + str(ROOT / ".venv/bin/python") + "\nfrom dotenv import dotenv_values\nprint(dotenv_values(" + repr(str(env_path)) + ")[\"POSTGRES_PASSWORD\"])\n")
    askpass.chmod(0o700)
    ssh_env = os.environ.copy()
    ssh_env.update(SSH_ASKPASS=str(askpass), SSH_ASKPASS_REQUIRE="force", DISPLAY="backupcenter-bootstrap")
    knownhosts = local / "postgres-knownhosts"
    if not knownhosts.exists():
        imported = Path("/private/tmp/backupcenter-postgres-knownhosts")
        if imported.exists():
            knownhosts.write_bytes(imported.read_bytes())
    args = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile="+str(knownhosts), "-o", "NumberOfPasswordPrompts=1", values["POSTGRES_USERNAME"]+"@"+parsed.hostname]

    def remote(command, body=""):
        response = subprocess.run(args+[command], input=(values["POSTGRES_PASSWORD"]+"\n"+body).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ssh_env, timeout=45)
        if response.returncode:
            raise RuntimeError("Remote PostgreSQL host operation failed")
        return response.stdout.decode()

    # No secret is included in command arguments. SQL is delivered over encrypted stdin.
    psql = "sudo -S -p '' runuser -u postgres -- psql -X -qAt -v ON_ERROR_STOP=1 -d postgres"
    status = remote(psql, "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='backupcenter'), EXISTS(SELECT 1 FROM pg_roles WHERE rolname='backupcenter_runtime');\n").strip()
    managed = values.get("BACKUPCENTER_DB_NAME")==DATABASE and values.get("BACKUPCENTER_DB_USER")==ROLE and bool(values.get("BACKUPCENTER_DB_PASSWORD"))
    if status != "f|f" and not managed:
        raise RuntimeError("Existing target resources are not managed by this project; refusing reuse")
    certificate = remote("sudo -S -p '' cat /etc/ssl/certs/ssl-cert-snakeoil.pem")
    if "-----BEGIN CERTIFICATE-----" not in certificate:
        raise RuntimeError("Database TLS certificate unavailable")
    ca = local / "postgres-ca.pem"
    ca.write_text(certificate)
    ca.chmod(0o600)
    password = values.get("BACKUPCENTER_DB_PASSWORD") if managed else secrets.token_urlsafe(36)
    settings = {"BACKUPCENTER_DB_HOST":parsed.hostname,"BACKUPCENTER_DB_PORT":"5432","BACKUPCENTER_DB_NAME":DATABASE,"BACKUPCENTER_DB_USER":ROLE,"BACKUPCENTER_DB_PASSWORD":password,"BACKUPCENTER_DB_SSLMODE":"verify-ca","BACKUPCENTER_DB_SSLROOTCERT":str(ca)}
    lines = [line for line in env_path.read_text().splitlines() if line.partition("=")[0] not in settings]
    env_path.write_text("\n".join(lines).rstrip()+"\n\n# Application PostgreSQL runtime (backend only).\n"+"".join(k+"="+json.dumps(v)+"\n" for k,v in settings.items()))
    env_path.chmod(0o600)
    # Generated password uses URL-safe characters; never interpolate user input into SQL.
    if not all(c.isalnum() or c in "_-" for c in password):
        raise RuntimeError("Unexpected runtime password encoding")
    sql = "SELECT pg_advisory_lock(73124411);\n"
    sql += "SELECT 'CREATE ROLE backupcenter_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD ''"+password+"'';' WHERE NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='backupcenter_runtime')\n\\gexec\n"
    sql += "SELECT 'CREATE DATABASE backupcenter TEMPLATE template0;' WHERE NOT EXISTS(SELECT 1 FROM pg_database WHERE datname='backupcenter')\n\\gexec\n"
    sql += "REVOKE ALL ON DATABASE backupcenter FROM PUBLIC;\nGRANT CONNECT ON DATABASE backupcenter TO backupcenter_runtime;\n"
    remote(psql, sql)
    kwargs={"host":parsed.hostname,"port":5432,"dbname":DATABASE,"user":ROLE,"password":password,"sslmode":"verify-ca","sslrootcert":str(ca),"connect_timeout":10}
    # Apply migrations as the host administrator; runtime role never owns schema/tables.
    admin = "sudo -S -p '' runuser -u postgres -- psql -X -qAt -v ON_ERROR_STOP=1 -d backupcenter"
    marker = remote(admin, "SELECT to_regclass('backupcenter.schema_migrations');\n").strip()
    for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
        version = migration.name
        if not all(c.isalnum() or c in "_." for c in version):
            raise RuntimeError("Invalid migration name")
        checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
        applied = remote(admin, "SELECT checksum FROM backupcenter.schema_migrations WHERE version='"+version+"';\n").strip() if marker else ""
        if applied:
            if applied != checksum: raise RuntimeError("Applied migration checksum mismatch")
            continue
        remote(admin, "BEGIN;\nSELECT pg_advisory_xact_lock(73124411);\nREVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"+migration.read_text()+"\nINSERT INTO backupcenter.schema_migrations(version,checksum) VALUES('"+version+"','"+checksum+"');\nCOMMIT;\n")
        marker = "present"
    grants = "BEGIN;\nGRANT USAGE ON SCHEMA backupcenter TO backupcenter_runtime;\n"
    for table in ["connections","workloads","session_observations","latest_snapshots","operation_requests","configuration_revisions","protection_assignments"]:
        grants += "GRANT SELECT,INSERT,UPDATE ON backupcenter."+table+" TO backupcenter_runtime;\n"
    grants += "GRANT SELECT,INSERT ON backupcenter.audit_events TO backupcenter_runtime;\nGRANT USAGE ON ALL SEQUENCES IN SCHEMA backupcenter TO backupcenter_runtime;\nCOMMIT;\n"
    remote("sudo -S -p '' runuser -u postgres -- psql -X -qAt -v ON_ERROR_STOP=1 -d backupcenter", grants)
    with closing(psycopg2.connect(**kwargs)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
            if not cursor.fetchone()[0]:
                raise RuntimeError("Expected TLS connection")
    print("Dedicated backupcenter database provisioned, migration verified, restricted runtime login and pinned-certificate TLS verified.")

if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as exc:
        print("Database bootstrap failed:", type(exc).__name__)
        sys.exit(1)
