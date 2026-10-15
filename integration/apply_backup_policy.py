"""Root-owned reviewed schedule/pool application; never starts jobs or cleanup."""
import fcntl,grp,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
from uuid import UUID
from active_policy_contract import ActivePolicy,schedule,patch_retention
from direct_vm_restore import console,require
NAMES={'PNET','MTIMRWCNTDEV','MTIMRWKF01','MTIMRWNTP01','MTIMRWNTP02','MTIMRWPGSQL01','MTIMRWZTNA01'}
BASE=Path('/etc/bareos/bareos-dir.d');ROOT=Path('/var/lib/bareos-policy-applications')
RETIRE=Path('/opt/bareos/25.1.1/lib/bareos/scripts/retire-vm-chains.py')
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def paths(vm):return BASE/'job'/(vm+'.conf'),BASE/'pool'/(vm+'.conf'),BASE/'schedule'/('BC-Policy-'+vm+'.conf')
def current():
    rows=[]
    for vm in sorted(NAMES):
        j,p,_=paths(vm);job=j.read_text();pool=p.read_text();match=re.search(r'^\s*Schedule\s*=\s*(\S+)',job,re.M)
        schedule_text=(BASE/'schedule'/(match.group(1)+'.conf')).read_text() if match else ''
        tm=re.search(r'at (\d{2}):(\d{2})',schedule_text);local_time=f"{(int(tm.group(1))+8)%24:02d}:{tm.group(2)}" if tm else None
        rows.append({'job':'VMware-'+vm,'timeWita':local_time,'automatic':not bool(re.search(r'Enabled\s*=\s*no',schedule_text)),'schedule':match.group(1) if match else None,'retentionDays':int(re.search(r'Volume Retention\s*=\s*(\d+) days',pool).group(1)),'maximumVolumes':int(re.search(r'Maximum Volumes\s*=\s*(\d+)',pool).group(1))})
    return {'jobs':rows,'cadence':'Full on 1 and 15; Incremental on all other days','timezone':'Asia/Makassar','minimumRetentionDays':30,'currentPolicyScope':'Existing seven managed VMware jobs'}
def plan(definition):
    d=ActivePolicy(**definition).model_dump();changes=[]
    for job in d['jobs']:
        require(job.startswith('VMware-') and job[7:] in NAMES,'Job is outside managed policy scope.');vm=job[7:];j,p,s=paths(vm);oldj=j.read_text();oldp=p.read_text();olds=s.read_text() if s.exists() else None
        require(re.search(r'Name\s*=\s*'+re.escape(job)+r'\s*$',oldj,re.M),'Job ownership mismatch.')
        schedule_name='BC-Policy-'+vm
        newj,n=re.subn(r'(?m)^(\s*Schedule\s*=).*$',' Schedule = '+schedule_name,oldj);require(n==1,'Expected one job schedule.')
        newp,n=re.subn(r'(?m)^(\s*Volume Retention\s*=).*$',' Volume Retention = '+str(d['retention_days'])+' days',oldp);require(n==1,'Expected one pool retention.')
        newp,n=re.subn(r'(?m)^(\s*Maximum Volumes\s*=).*$',' Maximum Volumes = '+str(d['maximum_volumes']),newp);require(n==1,'Expected one pool volume limit.')
        require('AutoPrune = no' in newp and 'Recycle = yes' in newp,'Pool cleanup invariants changed.')
        for path,old,new in ((j,oldj,newj),(p,oldp,newp),(s,olds,schedule(schedule_name,d['time_wita'],d['automatic']))):
            require(not path.is_symlink(),'Policy path cannot be a symlink.');changes.append({'path':str(path),'before':old,'after':new})
    old=RETIRE.read_text();new=patch_retention(old);compile(new,str(RETIRE),'exec');changes.append({'path':str(RETIRE),'before':old,'after':new})
    baseline=[{'path':c['path'],'beforeDigest':digest(c['before']) if c['before'] is not None else None,'afterDigest':digest(c['after'])} for c in changes]
    value={'definition':d,'files':baseline};sha=digest(json.dumps(value,sort_keys=True,separators=(',',':')))
    return {'definition':d,'reviewDigest':sha,'changes':changes,'cadence':'Full on 1 and 15; Incremental on other days','existingVolumePolicy':'Existing volume minima remain; cleanup uses the greater of Pool and Volume retention. Latest successful Full chain is preserved.','doesNotRun':'No backup, restore, prune or purge is executed by Apply.'}
def write(path,text):
    p=Path(path);fd,name=tempfile.mkstemp(prefix='.backupcenter-',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.chown(name,0,grp.getgrnam('bareos').gr_gid);os.chmod(name,0o750 if p==RETIRE else 0o640);os.replace(name,p)
    finally:Path(name).unlink(missing_ok=True)
def active():
    p=subprocess.run(['runuser','-u','bareos','--','psql','-X','-At','-d','bareos','-c',"SELECT count(*) FROM job WHERE jobstatus IN ('R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L');"],text=True,capture_output=True,check=True)
    require(p.stdout.strip()=='0','Wait for active or waiting Bareos jobs to finish before applying policy.')
def syntax():
    p=subprocess.run(['runuser','-u','bareos','--','/opt/bareos/25.1.1/sbin/bareos-dir','-t'],text=True,capture_output=True,cwd='/var/lib/bareos',timeout=30)
    require(p.returncode==0,'Director validation failed; configuration will be rolled back.')
def verify(definition):
    runtime=console('show jobs')['jobs']
    require(all(runtime.get(job,{}).get('schedule')=='BC-Policy-'+job[7:] for job in definition['jobs']),'Director did not load the reviewed job schedules.')
    names=','.join("'"+job[7:]+"'" for job in definition['jobs'])
    query="SELECT json_agg(json_build_object('retention',volretention,'maximum',maxvols)) FROM pool WHERE name IN ("+names+");"
    result=subprocess.run(['runuser','-u','bareos','--','psql','-X','-At','-d','bareos','-c',query],capture_output=True,text=True,check=True)
    rows=json.loads(result.stdout)
    require(rows and len(rows)==len(definition['jobs']) and all(int(r['retention'])==definition['retention_days']*86400 and int(r['maximum'])==definition['maximum_volumes'] for r in rows),'Catalog Pool defaults do not match the reviewed policy.')
def apply(body):
    rid=str(UUID(body['request_id']));ROOT.mkdir(mode=0o700,exist_ok=True);receipt=ROOT/(rid+'.json')
    with open('/var/lib/bareos/vm-chain-retention.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if receipt.exists():
            r=json.loads(receipt.read_text());require(r['reviewDigest']==body['digest'] and r['actor']==body['actor'] and r['definition']==ActivePolicy(**body['definition']).model_dump(),'Request key belongs to a different policy intent.');return r
        require(not any(json.loads(x.read_text()).get('state') in ('Dispatching','Unknown') for x in ROOT.glob('*.json')),'An unresolved policy application must be reconciled before a new request.')
        p=plan(body['definition']);require(p['reviewDigest']==body['digest'],'Policy changed since review. Review again.');active()
        r={'id':rid,'reviewDigest':body['digest'],'actor':body['actor'],'state':'Dispatching','definition':p['definition'],'changes':p['changes']}
        with receipt.open('x') as f:json.dump(r,f)
        receipt.chmod(0o600)
        try:
            for c in p['changes']:write(c['path'],c['after'])
            syntax();console('reload')
            for job in p['definition']['jobs']:console('update pool='+job[7:])
            verify(p['definition']);r['state']='Applied'
        except Exception:
            # Preserve failed receipts and before-images. Never run cleanup on rollback.
            for c in reversed(p['changes']):
                if c['before'] is None:Path(c['path']).unlink(missing_ok=True)
                else:write(c['path'],c['before'])
            try:
                syntax();console('reload')
                for job in p['definition']['jobs']:console('update pool='+job[7:])
                r['state']='Failed';r['message']='Apply failed; original configuration and Pool defaults restored.'
            except Exception:r['state']='Unknown';r['message']='Policy rollback unconfirmed. Inspect root receipt before further changes.'
        receipt.write_text(json.dumps(r));return r
if __name__=='__main__':
    try:
        require(os.geteuid()==0,'Administrator service required.');b=json.load(sys.stdin);action=b['action']
        if action=='current':require(set(b)=={'action'},'Unexpected parameters.');r=current()
        elif action=='preview':require(set(b)=={'action','definition'},'Unexpected parameters.');r=plan(b['definition'])
        elif action=='apply':require(set(b)=={'action','definition','request_id','digest','actor'},'Unexpected parameters.');r=apply(b)
        elif action=='status':require(set(b)=={'action','request_id'},'Unexpected parameters.');r=json.loads((ROOT/(str(UUID(b['request_id']))+'.json')).read_text())
        else:raise ValueError('Unsupported policy action.')
        print(json.dumps(r))
    except Exception as e:
        print(json.dumps({'error':str(e)[:200] if isinstance(e,ValueError) else 'Policy gateway unavailable; reconcile the receipt before retrying.'}));sys.exit(1)
