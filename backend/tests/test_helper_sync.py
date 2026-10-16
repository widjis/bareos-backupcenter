import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,"fcntl",types.SimpleNamespace(LOCK_EX=2,LOCK_NB=4,flock=lambda *a:None))
    monkeypatch.setitem(sys.modules,"grp",types.SimpleNamespace(getgrnam=lambda _:types.SimpleNamespace(gr_gid=0)))
    path=Path(__file__).resolve().parents[2]/"integration/sync_policy_helpers.py"
    spec=importlib.util.spec_from_file_location("sync_test",path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m.os,"geteuid",lambda:0,raising=False)
    a=tmp_path/"existing.py";a.write_text("original")
    b=tmp_path/"added.py"
    m.TARGETS={str(a):(0o700,"root"),str(b):(0o644,"root")}
    m.LOCK=tmp_path/"lock";m.POLICY_RECEIPTS=tmp_path/"receipts";m.POLICY_RECEIPTS.mkdir();m.BACKUP_ROOT=tmp_path/"backups"
    source=tmp_path/"source";source.mkdir()
    (source/"a.py").write_text("value=1\n");(source/"b.py").write_text("value=2\n")
    manifest=[dict(target=str(target),source=name,sha256=m.sha((source/name).read_bytes()),mode=mode,group="root") for target,name,mode in [(a,"a.py",0o700),(b,"b.py",0o644)]]
    baseline={"jobs":[dict(job="VMware-PNET",timeWita="21:30",automatic=True,retentionDays=30,maximumVolumes=6)],"executionReady":False}
    monkeypatch.setattr(m,"current",lambda:baseline)
    monkeypatch.setattr(m,"config_hashes",lambda:{"job":"same"})
    monkeypatch.setattr(m,"run",lambda *a,**kw:types.SimpleNamespace(stdout="0",stderr="",returncode=0))
    monkeypatch.setattr(m,"atomic",lambda path,data,*args:path.write_bytes(data))
    # Avoid changing the process-wide umask in this offline fixture.
    monkeypatch.setattr(m.os,"umask",lambda _:0)
    return m,source,manifest,a,b,baseline


def test_success_preserves_recovery_copy_and_does_not_enable_timer(fixture):
    m,source,manifest,a,b,baseline=fixture
    result=m.sync(manifest,source,True)
    assert a.read_text()=="value=1\n" and b.read_text()=="value=2\n"
    backup=Path(result["backup_directory"])
    saved=next((backup/"files").rglob("existing.py"))
    assert saved.read_text()=="original"
    assert result["timer_activated"] is False and result["execution_ready"] is False


def test_failed_readback_restores_before_image_and_removes_only_added_target(fixture,monkeypatch):
    m,source,manifest,a,b,baseline=fixture
    calls=iter([baseline,{**baseline,"executionReady":True}])
    monkeypatch.setattr(m,"current",lambda:next(calls))
    with pytest.raises(RuntimeError,match="private rollback receipt"):
        m.sync(manifest,source,True)
    assert a.read_text()=="original" and not b.exists()
    assert json.loads(next(m.BACKUP_ROOT.rglob("receipt.json")).read_text())["state"]=="RolledBack"


def test_candidate_hash_mismatch_never_changes_target(fixture):
    m,source,manifest,a,b,baseline=fixture
    (source/"a.py").write_text("tampered=1")
    with pytest.raises(ValueError,match="checksum"):
        m.sync(manifest,source,True)
    assert a.read_text()=="original" and not b.exists() and not m.BACKUP_ROOT.exists()
