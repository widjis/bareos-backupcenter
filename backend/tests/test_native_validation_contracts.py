import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.skipif(os.name != "nt",reason="Linux validation is explicitly operator-run, never auto-executed against installed Director/systemd")
@pytest.mark.parametrize("filename",["check_director_candidate.py","check_drain_systemd.py"])
def test_native_operator_harness_rejects_windows_without_effects(filename):
    result=subprocess.run([sys.executable,str(ROOT/"integration"/filename)],capture_output=True,text=True,timeout=10)
    assert result.returncode==2
    assert json.loads(result.stdout).get("unsupported") or json.loads(result.stdout).get("status")=="unsupported"
