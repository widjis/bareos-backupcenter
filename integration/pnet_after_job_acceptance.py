"""Explicit one-shot PNET acceptance using an unscheduled temporary Admin source.
No other VM, policy Apply, production schedule or production drain activation.
A root-owned receipt prevents blind resubmission. Cleanup removes only the exact
fixture file it created after validating its digest and original config hashes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

BASE=Path("/etc/bareos/bareos-dir.d")
TARGET="VMware-PNET"
ACTIVE="'R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L'"


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(data):return hashlib.sha256(data).hexdigest()


def sql(query):
    result=subprocess.run(["runuser","-u","bareos","--","psql","-X","-At","-d","bareos","-c",query],capture_output=True,text=True,check=True,timeout=30)
    return result.stdout.strip()


def configs():return {str(p):digest(p.read_bytes()) for p in BASE.glob("*/*.conf")}


def save(path,row):
    import tempfile
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".acceptance-")
    try:
        with os.fdopen(fd,"w") as f:json.dump(row,f);f.flush();os.fsync(f.fileno())
        os.chmod(name,0o600);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def jobid(data):
    found=[]
    def walk(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key.lower()=="jobid" and type(item) is int and item>0:found.append(item)
                else:walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    walk(data)
    require(len(set(found))==1,"Source JobId not confirmed; do not resend")
    return found[0]


def main(action,key):
    require(os.name=="posix" and os.geteuid()==0,"Linux root acceptance only")
    key=str(UUID(key));root=Path("/var/lib")/("bareos-pnet-acceptance-"+key)
    record=root/"acceptance.json";source="VMware-PNET-ACCEPTANCE-"+key[:8].upper()
    fixture=BASE/"job"/(source+".conf")
    sys.path.insert(0,"/opt/bareos-api")
    import apply_backup_policy as policy
    from direct_vm_restore import console
    if action=="prepare":
        require(not record.exists() and not fixture.exists(),"Acceptance already prepared; inspect existing receipt")
        require(sql(f"SELECT count(*) FROM job WHERE jobstatus IN ({ACTIVE});")=="0","Wait for active/waiting jobs")
        import pwd
        account=pwd.getpwnam("bareos");root.mkdir(mode=0o700);os.chown(root,account.pw_uid,account.pw_gid);root.chmod(0o700)
        before=configs();baseline=int(sql("SELECT coalesce(max(jobid),0) FROM job;"))
        command=f"/opt/bareos-api-venv/bin/python /opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py --source {source} --source-job-id %i --target {TARGET} --level incremental --window-start 00:00 --window-end 23:59 --state-dir {root}/runtime"
        content=f'Job {{\n Name = {source}\n Type = Admin\n Client = bareos-fd\n FileSet = VMware-PNET\n Storage = SMB-PNET\n Pool = PNET\n Messages = Standard\n Run After Job = "{command}"\n}}\n'
        row={"state":"Preparing","source":source,"target":TARGET,"baseline_max_jobid":baseline,"config_before":before,"fixture_digest":digest(content.encode()),"manual_test_window":"00:00-23:59; production calendars unchanged"}
        save(record,row)
        try:
            policy.write(str(fixture),content);policy.syntax();console("reload")
            row["state"]="Prepared";save(record,row)
        except Exception:
            if fixture.exists() and digest(fixture.read_bytes())==row["fixture_digest"]:fixture.unlink()
            policy.syntax();console("reload");row["state"]="PreparationFailed";save(record,row);raise
        return {"state":row["state"],"source":source,"acceptance_directory":str(root),"production_schedules_changed":False}
    require(record.is_file(),"Acceptance is not prepared")
    row=json.loads(record.read_text())
    if action=="dispatch":
        require(row["state"]=="Prepared","Receipt is not Prepared; inspect status, never blindly resend")
        require(sql(f"SELECT count(*) FROM job WHERE jobstatus IN ({ACTIVE});")=="0","Wait for active/waiting jobs")
        row["state"]="Dispatching";save(record,row)
        try:row["source_jobid"]=jobid(console("run job="+source+" yes"));row["state"]="Accepted"
        except Exception:row["state"]="Unknown";save(record,row);raise
        save(record,row);return {key:row.get(key) for key in ("state","source","source_jobid","target")}
    if action=="reconcile":
        require(row["state"] in ("Unknown","Dispatching"),"Only uncertain source submission can be reconciled")
        ids=sql(f"SELECT jobid FROM job WHERE name='{source}' AND type='D' AND jobid>{row['baseline_max_jobid']};").splitlines()
        require(len(ids)==1,"Source identity is not uniquely reconciled; do not resend")
        source_id=int(ids[0]);receipts=list((root/"runtime/receipts").glob("*.json"));require(len(receipts)==1,"Native receipt not uniquely available")
        native=json.loads(receipts[0].read_text())
        require(native.get("source")==source and native.get("sourceJobId")==source_id and native.get("target")==TARGET,"Catalog/receipt source binding mismatch")
        row.update(source_jobid=source_id,state="Accepted",source_submission_reconciled=True);save(record,row)
        return {"state":"Accepted","source_jobid":source_id,"source_submission_reconciled":True,"resubmitted":False}
    if action in ("status","replay","cleanup"):
        receipts=list((root/"runtime/receipts").glob("*.json"));require(len(receipts)<=1,"Unexpected runtime receipt count")
        native=json.loads(receipts[0].read_text()) if receipts else None
        result={key:row.get(key) for key in ("state","source","source_jobid","target")}
        if native:
            require(native["source"]==source and native["target"]==TARGET and native["sourceJobId"]==row.get("source_jobid"),"Native source substitution/target identity mismatch")
            result["runtime_state"]=native["state"];result["source_jobid_substitution_verified"]=True
            target_id=native.get("queuedJobId")
            if target_id:
                require(type(target_id) is int and target_id>0,"Invalid target JobId")
                target=sql(f"SELECT row_to_json(x) FROM (SELECT jobid,name,level,jobstatus,joberrors,jobbytes,jobfiles,starttime,endtime FROM job WHERE jobid={target_id}) x;")
                target=json.loads(target);require(target["name"]==TARGET,"Queued JobId does not belong to PNET")
                result["target_job"]=target
        if action=="status":return result
        require(native and native.get("queuedJobId"),"Target acknowledgement not available")
        target=result["target_job"]
        require(target["jobstatus"] in ("T","W","E","e","f","A"),"Wait for target to finish")
        if action=="replay":
            args=["runuser","-u","bareos","--","/opt/bareos-api-venv/bin/python","/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py","--source",source,"--source-job-id",str(row["source_jobid"]),"--target",TARGET,"--level","incremental","--window-start","00:00","--window-end","23:59","--state-dir",str(root/"runtime")]
            again=subprocess.run(args,capture_output=True,text=True,check=True,timeout=45);again=json.loads(again.stdout)
            count=int(sql(f"SELECT count(*) FROM job WHERE name='{TARGET}' AND jobid>{row['baseline_max_jobid']};"))
            require(again.get("queuedJobId")==native["queuedJobId"] and count==1,"Replay created or observed an unexpected target run")
            row["replay_verified"]=True;save(record,row);return {**result,"replay_verified":True,"pnet_runs_since_prepare":count}
        require(sql(f"SELECT count(*) FROM job WHERE name='{source}' AND jobstatus IN ({ACTIVE});")=="0","Source job remains active")
        require(fixture.exists() and digest(fixture.read_bytes())==row["fixture_digest"],"Fixture changed; refuse cleanup")
        fixture.unlink();policy.syntax();console("reload")
        require(configs()==row["config_before"],"Original configuration hashes changed")
        row["state"]="Cleaned";row["result"]=result;save(record,row)
        return {**result,"fixture_removed":True,"original_config_unchanged":True,"acceptance_directory":str(root)}
    raise ValueError("Unknown acceptance action")


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("action",choices=("prepare","dispatch","reconcile","status","replay","cleanup"));parser.add_argument("--id",required=True);args=parser.parse_args()
    try:print(json.dumps(main(args.action,args.id),default=str))
    except Exception as exc:print(json.dumps({"error":str(exc) if isinstance(exc,ValueError) else "Acceptance check failed; inspect existing receipt before any retry"}));raise SystemExit(1)
