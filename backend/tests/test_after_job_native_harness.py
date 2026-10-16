import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "integration" / "check_after_job_native.py"


def test_harness_contract_matches_platform():
    result = subprocess.run([sys.executable, str(HARNESS)], text=True, capture_output=True)
    payload = json.loads(result.stdout.strip())
    if os.name == "nt":
        assert result.returncode == 2
        assert payload == {"ok": False, "unsupported": "posix-only"}
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert payload["ok"] is True


def test_harness_source_stays_isolated_and_small():
    source = HARNESS.read_text(encoding="utf-8")
    assert "TemporaryDirectory(" in source
    assert "after_job_runtime.py" in source
    assert "/etc" not in source and "/var/lib" not in source
    assert "rmtree(" not in source
    assert len(source.splitlines()) <= 220


def test_harness_compiles():
    result = subprocess.run([sys.executable, "-m", "py_compile", str(HARNESS)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
