"""Migration safety checks use a ledger adapter, never a live administrator."""
import hashlib
import re
from pathlib import Path

import pytest
from scripts.apply_lifecycle_migrations import MigrationError, VERSIONS, inspect_or_apply


class Ledger:
    def __init__(self):
        self.rows = {}
        self.writes = []
        self.fail_after_commit = False
    def sql(self, text):
        if "to_regclass" in text:
            return "t"
        if text.startswith("SELECT checksum"):
            key = re.search("version='([^']+)'", text)[1]
            return self.rows.get(key, "")
        assert text.startswith("BEGIN;") and text.endswith("COMMIT;")
        assert "pg_advisory_xact_lock(73124411)" in text
        assert "Unresolved application operations" in text
        version, checksum = re.search(r"VALUES\('([^']+)','([^']+)'\)", text).groups()
        self.writes.append(version)
        self.rows[version] = checksum
        if self.fail_after_commit:
            raise MigrationError("Lost acknowledgement. Read-only reconciliation required.")
        return ""


@pytest.fixture
def migrations(tmp_path):
    for i, version in enumerate(VERSIONS):
        (tmp_path / version).write_text(f"CREATE TABLE backupcenter.test_lifecycle_{i} (id uuid PRIMARY KEY);\n")
    return tmp_path


def test_read_only_then_apply_then_replay_without_duplicate_ddl(migrations):
    ledger = Ledger()
    assert {row["state"] for row in inspect_or_apply(ledger, migration_dir=migrations)} == {"pending"}
    assert ledger.writes == []
    assert {row["state"] for row in inspect_or_apply(ledger, apply=True, migration_dir=migrations)} == {"applied"}
    assert ledger.writes == list(VERSIONS)
    assert {row["state"] for row in inspect_or_apply(ledger, apply=True, migration_dir=migrations)} == {"verified"}
    assert ledger.writes == list(VERSIONS)


def test_all_files_and_ledger_are_validated_before_any_write(migrations):
    ledger = Ledger()
    ledger.rows[VERSIONS[1]] = "wrong checksum"
    with pytest.raises(MigrationError, match="different checksum"):
        inspect_or_apply(ledger, apply=True, migration_dir=migrations)
    assert ledger.writes == []
    ledger.rows.clear()
    (migrations / VERSIONS[1]).write_text("DROP TABLE backupcenter.workloads;")
    with pytest.raises(MigrationError, match="additive"):
        inspect_or_apply(ledger, apply=True, migration_dir=migrations)
    assert ledger.writes == []


def test_unknown_ack_stops_and_read_only_reconciles_without_resend(migrations):
    ledger = Ledger()
    ledger.fail_after_commit = True
    with pytest.raises(MigrationError, match="acknowledgement"):
        inspect_or_apply(ledger, apply=True, migration_dir=migrations)
    assert ledger.writes == [VERSIONS[0]]
    rows = inspect_or_apply(ledger, migration_dir=migrations)
    assert rows[0]["state"] == "verified"
    assert rows[1]["state"] == "pending"
    assert ledger.writes == [VERSIONS[0]]
