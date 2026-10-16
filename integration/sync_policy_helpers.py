"""Pinned-source atomic helper synchronization; no schedule Apply or backup dispatch.
Run on the existing Linux server with --manifest and --source-root. Dry-run by
default; --install backs up exact before-images, validates read-back and rolls
back on failure. Production timer activation is explicitly outside this tool.
"""
import argparse
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

TARGETS = {
    "/opt/bareos-api/active_policy_contract.py": (0o644, "root"),
    "/opt/bareos-api/policy_hooks.py": (0o644, "root"),
    "/opt/bareos-api/after_job_runtime.py": (0o644, "root"),
    "/opt/bareos-api/apply_backup_policy.py": (0o700, "root"),
    "/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py": (0o750, "bareos"),
    "/etc/systemd/system/backupcenter-after-job-drain.service": (0o644, "root"),
    "/etc/systemd/system/backupcenter-after-job-drain.timer": (0o644, "root"),
}
LOCK = Path("/var/lib/bareos/vm-chain-retention.lock")
POLICY_RECEIPTS = Path("/var/lib/bareos-policy-applications")
BACKUP_ROOT = Path("/root/backupcenter-helper-sync")
ACTIVE = "'R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L'"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, check=True, timeout=45, **kwargs)


def current():
    result = run(["/opt/bareos-api-venv/bin/python", "/opt/bareos-api/apply_backup_policy.py"], input=json.dumps({"action":"current"}))
    return json.loads(result.stdout)


def baseline(rows):
    keys = ("job", "timeWita", "automatic", "retentionDays", "maximumVolumes")
    return sorted([{key:row[key] for key in keys} for row in rows["jobs"]], key=lambda row:row["job"])


def config_hashes():
    return {str(p):sha(p.read_bytes()) for p in Path("/etc/bareos/bareos-dir.d").glob("*/*.conf")}


def atomic(path, data, mode, uid, gid):
    fd, name = tempfile.mkstemp(prefix=".backupcenter-sync-", dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chown(name,uid,gid);os.chmod(name,mode);os.replace(name,path)
        directory=os.open(path.parent,os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:Path(name).unlink(missing_ok=True)


def sync(manifest, source_root, install=False):
    require(os.geteuid()==0,"Root synchronization required")
    require(len(manifest)==len(TARGETS) and {row["target"] for row in manifest}==set(TARGETS),"Exact helper target set required")
    payload=[]
    for row in manifest:
        path=Path(row["target"]);source=(source_root/row["source"]).resolve()
        require(source.is_relative_to(source_root.resolve()),"Source must stay within candidate root")
        require(not path.is_symlink() and path.parent.is_dir(),"Unsafe target path")
        data=source.read_bytes()
        require(sha(data)==row["sha256"],"Candidate source checksum mismatch")
        require((row["mode"],row["group"])==TARGETS[str(path)],"Target ownership/mode differs from contract")
        if path.suffix==".py":compile(data,str(path),"exec")
        payload.append((row,data))
    with open(LOCK,"a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        count=run(["runuser","-u","bareos","--","psql","-X","-At","-d","bareos","-c",f"SELECT count(*) FROM job WHERE jobstatus IN ({ACTIVE});"]).stdout.strip()
        require(count=="0","Active/waiting jobs prevent synchronization")
        require(not any(json.loads(p.read_text()).get("state") in ("Dispatching","Unknown") for p in POLICY_RECEIPTS.glob("*.json")),"Unresolved policy receipt prevents synchronization")
        before_jobs=baseline(current());before_configs=config_hashes()
        if not install:
            return {"dry_run":True,"targets":len(payload),"jobs":len(before_jobs),"candidate_hashes_verified":True}
        os.umask(0o077)
        backup=BACKUP_ROOT/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8])
        backup.mkdir(parents=True,mode=0o700)
        entries=[]
        for row,_ in payload:
            path=Path(row["target"]);entry={**row,"before_exists":path.exists()}
            if path.exists():
                meta=path.stat();entry.update(before_sha256=sha(path.read_bytes()),before_mode=stat.S_IMODE(meta.st_mode),before_uid=meta.st_uid,before_gid=meta.st_gid)
                saved=backup/"files"/path.relative_to(path.anchor);saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
            entries.append(entry)
        receipt={"state":"Prepared","files":entries,"jobs_before":before_jobs,"config_hashes_before":before_configs}
        record=backup/"receipt.json";record.write_text(json.dumps(receipt,indent=2))
        try:
            for row,data in payload:
                atomic(Path(row["target"]),data,row["mode"],0,grp.getgrnam(row["group"]).gr_gid)
            after=current()
            require(baseline(after)==before_jobs,"Current schedule/retention read-back changed")
            require(after.get("executionReady") is False,"Broad Apply must stay blocked")
            require(config_hashes()==before_configs,"Production configuration files changed")
            run(["systemd-analyze","verify","/etc/systemd/system/backupcenter-after-job-drain.service","/etc/systemd/system/backupcenter-after-job-drain.timer"])
            run(["systemctl","daemon-reload"])
            receipt.update(state="Installed",config_unchanged=True,execution_ready=False)
        except Exception:
            for entry in reversed(entries):
                path=Path(entry["target"])
                if entry["before_exists"]:
                    saved=backup/"files"/path.relative_to(path.anchor);atomic(path,saved.read_bytes(),entry["before_mode"],entry["before_uid"],entry["before_gid"])
                else:path.unlink(missing_ok=True)
            try:run(["systemctl","daemon-reload"]);receipt["state"]="RolledBack"
            except Exception:receipt["state"]="Unknown"
            record.write_text(json.dumps(receipt,indent=2));raise RuntimeError("Synchronization failed; inspect private rollback receipt")
        record.write_text(json.dumps(receipt,indent=2))
        return {"state":receipt["state"],"backup_directory":str(backup),"targets":len(entries),"jobs":len(before_jobs),"config_unchanged":True,"execution_ready":False,"timer_activated":False}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",required=True);parser.add_argument("--source-root",required=True);parser.add_argument("--install",action="store_true");args=parser.parse_args()
    try:print(json.dumps(sync(json.loads(Path(args.manifest).read_text()),Path(args.source_root),args.install)))
    except Exception as exc:print(json.dumps({"error":str(exc) if isinstance(exc,(ValueError,RuntimeError)) else "Helper synchronization failed; inspect private receipt"}));raise SystemExit(1)
