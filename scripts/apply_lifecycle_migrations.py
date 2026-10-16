"""Apply only reviewed additive lifecycle migrations through the existing pinned SSH host.

Default is read-only. Does not rewrite credentials, roles, certificates or legacy tables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ("010_managed_registry.sql", "011_lifecycle_journal.sql")


class MigrationError(RuntimeError):
    pass


def trusted_host_fingerprint(host: str, known_hosts: Path, run=subprocess.run) -> str:
    if not known_hosts.is_file():
        raise MigrationError("Existing trusted PostgreSQL SSH host key is unavailable.")
    found = run(["ssh-keygen", "-F", host, "-f", str(known_hosts)], capture_output=True, timeout=10)
    keys = b"\n".join(line for line in found.stdout.splitlines() if line and not line.startswith(b"#"))
    if found.returncode or not keys:
        raise MigrationError("PostgreSQL SSH host is not present in the existing trust store.")
    with tempfile.NamedTemporaryFile(suffix=".pub", delete=False) as handle:
        key_path = Path(handle.name)
        handle.write(keys + b"\n")
    try:
        result = run(["ssh-keygen", "-l", "-E", "sha256", "-f", str(key_path)], capture_output=True, timeout=10)
        hashes = re.findall(rb"SHA256:[A-Za-z0-9+/]+", result.stdout)
        if result.returncode or not hashes:
            raise MigrationError("Trusted PostgreSQL SSH fingerprint could not be verified.")
        return hashes[0].decode("ascii")
    finally:
        key_path.unlink(missing_ok=True)


class PinnedPostgresAdmin:
    def __init__(self, values: dict, run=subprocess.run):
        self.run = run
        parsed = urlparse(values.get("POSTGRES_HOST", "") if "://" in values.get("POSTGRES_HOST", "") else "//" + values.get("POSTGRES_HOST", ""))
        self.host = parsed.hostname or ""
        self.port = parsed.port or 22
        self.username = values.get("POSTGRES_USERNAME", "")
        self.password = values.get("POSTGRES_PASSWORD", "")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.host) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", self.username) or not self.password:
            raise MigrationError("Configured PostgreSQL host administrator is unavailable.")
        if "\n" in self.password or "\r" in self.password:
            raise MigrationError("Configured host credentials cannot use multiline input.")
        self.fingerprint = None
        for candidate in (ROOT / ".local/postgres-knownhosts", Path.home() / ".ssh/known_hosts"):
            if not candidate.is_file():
                continue
            try:
                self.fingerprint = trusted_host_fingerprint(self.host, candidate, run)
                break
            except MigrationError:
                continue
        if self.fingerprint is None:
            raise MigrationError("PostgreSQL host is absent from existing project/user SSH trust stores. No connection attempted.")

    def sql(self, body: str) -> str:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".pw", delete=False) as handle:
            pw_path = Path(handle.name)
            handle.write(self.password)
        try:
            pw_path.chmod(0o600)
            args = [r"C:\Program Files\PuTTY\plink.exe", "-batch", "-ssh", "-P", str(self.port), "-hostkey", self.fingerprint, "-pwfile", str(pw_path), self.username + "@" + self.host,
                    "sudo -S -p '' runuser -u postgres -- psql -X -qAt -v ON_ERROR_STOP=1 -d backupcenter"]
            try:
                result = self.run(args, input=(self.password + "\n" + body + "\n").encode(), capture_output=True, timeout=45)
            except subprocess.TimeoutExpired:
                raise MigrationError("Migration transport timed out. Re-run read-only inspection before any apply; no automatic resend.") from None
            if result.returncode:
                raise MigrationError("Pinned PostgreSQL administration failed; raw diagnostics are withheld.")
            return result.stdout.decode("utf-8").strip()
        finally:
            pw_path.unlink(missing_ok=True)


def validate_additive_sql(text: str) -> None:
    # Fixed reviewed table-creation migrations only; reject credential/legacy mutation.
    clean = re.sub(r"--[^\n]*", "", text)
    if re.search(r"\b(DROP|TRUNCATE|DELETE\s+FROM|ALTER|PASSWORD|CREATE\s+(?:ROLE|DATABASE|USER))\b", clean, re.I):
        raise MigrationError("Lifecycle migration is outside the additive table/index/grant boundary.")


def inspect_or_apply(admin, *, apply=False, migration_dir=None):
    directory = migration_dir or ROOT / "backend/migrations"
    if admin.sql("SELECT to_regclass('backupcenter.schema_migrations') IS NOT NULL;") != "t":
        raise MigrationError("Existing managed application migration ledger is required.")
    plans = []
    for version in VERSIONS:
        path = directory / version
        if not path.is_file():
            raise MigrationError("Lifecycle migration candidates are not complete.")
        raw = path.read_bytes()
        sql = raw.decode("utf-8-sig")
        validate_additive_sql(sql)
        checksum = hashlib.sha256(raw).hexdigest()
        query = "SELECT checksum FROM backupcenter.schema_migrations WHERE version='" + version + "';"
        observed = admin.sql(query)
        if observed and observed != checksum:
            raise MigrationError("An applied lifecycle migration has a different checksum. No changes made.")
        plans.append((version, sql, checksum, observed, query))
    results = []
    for version, sql, checksum, observed, query in plans:
        state = "verified" if observed else "pending"
        if apply and not observed:
            # The marker is rechecked while holding the same transaction lock as bootstrap.
            guard = "DO $guard$ BEGIN IF EXISTS (SELECT 1 FROM backupcenter.schema_migrations WHERE version='" + version + "') THEN RAISE EXCEPTION 'Migration ledger changed; inspect before apply'; END IF; IF EXISTS (SELECT 1 FROM backupcenter.operation_requests WHERE state IN ('Prepared','Dispatching','Accepted','Running','Unknown')) THEN RAISE EXCEPTION 'Unresolved application operations'; END IF; END $guard$;"
            statement = "BEGIN;\nSELECT pg_advisory_xact_lock(73124411);\n" + guard + "\n" + sql + "\nINSERT INTO backupcenter.schema_migrations(version,checksum) VALUES('" + version + "','" + checksum + "');\nCOMMIT;"
            admin.sql(statement)
            if admin.sql(query) != checksum:
                raise MigrationError("Migration acknowledgement was not confirmed. Inspect the ledger before another apply.")
            state = "applied"
        results.append({"version": version, "state": state, "checksum": checksum})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply only the two reviewed additive lifecycle migrations.")
    args = parser.parse_args()
    try:
        rows = inspect_or_apply(PinnedPostgresAdmin(dotenv_values(ROOT / ".env")), apply=args.apply)
        print(json.dumps({"mode": "apply" if args.apply else "read_only", "migrations": rows}))
    except MigrationError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    except Exception:
        print(json.dumps({"error": "Lifecycle migration check failed; inspect prerequisites. Raw credentials and diagnostics withheld."}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
