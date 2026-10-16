"""Root-owned reviewed schedule/pool application; never starts jobs or cleanup."""
import fcntl,grp,hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
from uuid import UUID
from active_policy_contract import ActivePolicy,schedule,calendar_schedule,ScheduleCalendar,patch_retention
from direct_vm_restore import console,require
from policy_hooks import verify_dependency_hooks
NAMES={'PNET','MTIMRWCNTDEV','MTIMRWKF01','MTIMRWNTP01','MTIMRWNTP02','MTIMRWPGSQL01','MTIMRWZTNA01'}
BASE=Path('/etc/bareos/bareos-dir.d');ROOT=Path('/var/lib/bareos-policy-applications')
RETIRE=Path('/opt/bareos/25.1.1/lib/bareos/scripts/retire-vm-chains.py')
TRIGGER=Path('/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py')
ACTIVE_STATUSES="'R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L'"
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def paths(vm):return BASE/'job'/(vm+'.conf'),BASE/'pool'/(vm+'.conf'),BASE/'schedule'/('BC-Policy-'+vm+'.conf')
def schedule_runs(text):return [line.strip() for line in text.splitlines() if re.match(r'^\s*Run\s*=',line)]
def policy_marker(text):
    marker=re.search(r'^# BackupCenter policy: (.+)$',text,re.M)
    return ActivePolicy(**json.loads(marker.group(1))).model_dump() if marker else None
def set_directive(text,name,value):
    pattern=rf'(?m)^\s*{re.escape(name)}\s*=.*\n?'
    line='' if value is None else f' {name} = {value}\n'
    if re.search(pattern,text):return re.sub(pattern,line,text)
    if value is None:return text
    return re.sub(r'(?m)^}\s*$',line+'}',text,count=1)
def set_marker(text,payload):
    pattern=r'(?m)^# BackupCenter policy: .*\n?'
    line='# BackupCenter policy: '+json.dumps(payload,sort_keys=True,separators=(',',':'))+'\n'
    if re.search(pattern,text):return re.sub(pattern,line,text)
    return re.sub(r'(?m)^}\s*$',line+'}',text,count=1)
def drop_dependency_block(text,target):
    pattern=rf'(?ms)^# BackupCenter dependency trigger begin: {re.escape(target)}\n.*?^# BackupCenter dependency trigger end: {re.escape(target)}\n?'
    return re.sub(pattern,'',text)
def dependency_block(target,definition):
    command=f'/opt/bareos-api-venv/bin/python {TRIGGER} --source {definition["after_job"]["source_job"]} --source-job-id %i --target {target} --level {definition["after_job"]["level"]} --window-start {definition["time_wita"]}'
    if definition.get('window_end_wita'):command+=' --window-end '+definition['window_end_wita']
    run=f' Run After Job = "{command}"\n'
    failed=f' Run After Failed Job = "{command}"\n' if definition['after_job']['on_failure']=='run_anyway' else ''
    return f'# BackupCenter dependency trigger begin: {target}\n{run}{failed}# BackupCenter dependency trigger end: {target}\n'
def add_dependency_block(text,target,definition):
    return re.sub(r'(?m)^}\s*$',lambda _:dependency_block(target,definition)+'}',drop_dependency_block(text,target),count=1)
def trigger_script():
    source=Path(__file__).with_name('after_job_runtime.py').read_text()
    compile(source,'after_job_runtime.py','exec')
    return source

def verify_retry_directives(text,definition):
    expected={'Reschedule On Error':'yes' if definition['retry_count'] else 'no',
              'Reschedule Times':str(definition['retry_count']) if definition['retry_count'] else None,
              'Reschedule Interval':str(definition['retry_interval_minutes']*60) if definition['retry_count'] else None,
              'Rerun Failed Levels':'yes' if definition['retry_count'] else None}
    for key,wanted in expected.items():
        found=re.findall(rf'^\s*{re.escape(key)}\s*=\s*([^\n]+)',text,re.M)
        if wanted=='no' and not found:continue
        require(found==([] if wanted is None else [wanted]),'Retry directives differ from reviewed policy; inspect configuration before editing.')

def verify_hooks(jobs,target,definition):
    verify_dependency_hooks({'VMware-'+vm:text for vm,text in jobs.items()},target,definition,dependency_block(target,definition) if definition['trigger_mode']=='after_job' else '')

def job_definition(vm,job,pool,schedule_text):
    base=policy_marker(job)
    if base:return base
    match=re.search(r'^\s*Schedule\s*=\s*(\S+)',job,re.M)
    local_time=None
    if schedule_text:
        tm=re.search(r'at (\d{2}):(\d{2})',schedule_text)
        local_time=f"{(int(tm.group(1))+8)%24:02d}:{tm.group(2)}" if tm else '21:30'
    marker=re.search(r'^# BackupCenter schedule: (.+)$',schedule_text,re.M) if schedule_text else None
    legacy=re.search(r'^# BackupCenter calendar: (.+)$',schedule_text,re.M) if schedule_text else None
    calendar=(json.loads(marker.group(1)).get('calendar') if marker else (json.loads(legacy.group(1)) if legacy else None))
    window=(json.loads(marker.group(1)).get('windowEndWita') if marker else None) if marker else None
    return ActivePolicy(**{'jobs':['VMware-'+vm],'time_wita':local_time or '21:30','retention_days':int(re.search(r'Volume Retention\s*=\s*(\d+) days',pool).group(1)),'maximum_volumes':int(re.search(r'Maximum Volumes\s*=\s*(\d+)',pool).group(1)),'automatic':not bool(schedule_text and re.search(r'Enabled\s*=\s*no',schedule_text)),'calendar':calendar,'window_end_wita':window} | ({'trigger_mode':'calendar'} if match else {})).model_dump()
def ensure_cycle_free(definitions):
    graph={job:definition['after_job']['source_job'] for job,definition in definitions.items() if definition['trigger_mode']=='after_job'}
    for start in graph:
        seen=set();node=start
        while node in graph:
            require(node not in seen,'After-job dependencies cannot create a cycle.')
            seen.add(node);node=graph[node]
def current():
    rows=[];definitions={}
    jobs={vm:paths(vm)[0].read_text() for vm in sorted(NAMES)}
    for vm in sorted(NAMES):
        j,p,s=paths(vm);job=jobs[vm];pool=p.read_text();match=re.search(r'^\s*Schedule\s*=\s*(\S+)',job,re.M)
        schedule_text=(BASE/'schedule'/(match.group(1)+'.conf')).read_text() if match else ''
        definition=job_definition(vm,job,pool,schedule_text);definitions['VMware-'+vm]=definition
        verify_retry_directives(job,definition)
        verify_hooks(jobs,'VMware-'+vm,definition)
        if definition['trigger_mode']=='calendar':
            require(match,'Current job schedule is missing.')
            expected=calendar_schedule('BC-Readback',definition['time_wita'],definition['automatic'],definition.get('calendar'),definition.get('window_end_wita'))
            require(schedule_runs(schedule_text)==schedule_runs(expected),'Current schedule is not a recognized dashboard calendar; inspect configuration before editing.')
        else:
            require(not match or match.group(1)=='Manual','After-job scheduling must not keep a managed clock schedule.')
            source=definition['after_job']['source_job'];source_text=jobs[source[7:]]
            require(f'# BackupCenter dependency trigger begin: VMware-{vm}' in source_text,'Current after-job dependency is incomplete; inspect configuration before editing.')
        rows.append({'calendar':definition.get('calendar'),'job':'VMware-'+vm,'timeWita':definition['time_wita'],'automatic':definition['automatic'],'retentionDays':definition['retention_days'],'maximumVolumes':definition['maximum_volumes'],'triggerMode':definition['trigger_mode'],'afterJob':definition.get('after_job'),'windowEndWita':definition.get('window_end_wita'),'retryCount':definition.get('retry_count',0),'retryIntervalMinutes':definition.get('retry_interval_minutes',30),'schedule':match.group(1) if match else 'Manual'})
    ensure_cycle_free(definitions)
    return {'jobs':rows,'cadence':'Per-job calendars and after-job chains; legacy jobs use Full on 1 and 15 and Incremental on other days','timezone':'Asia/Makassar','minimumRetentionDays':30,'currentPolicyScope':'Existing seven managed VMware jobs','executionReady':False,'executionBlockers':['Native trigger, deferred-drain and restart acceptance are not completed.']}
def plan(definition):
    observed=current()  # Reject drift before constructing any reviewed mutation.
    d=ActivePolicy(**definition).model_dump();changes=[];jobs={vm:paths(vm)[0].read_text() for vm in sorted(NAMES)};schedules={vm:(paths(vm)[2].read_text() if paths(vm)[2].exists() else None) for vm in sorted(NAMES)};definitions={}
    for vm in sorted(NAMES):
        definitions['VMware-'+vm]=job_definition(vm,jobs[vm],paths(vm)[1].read_text(),schedules[vm] or '')
    for target in d['jobs']:
        require(target.startswith('VMware-') and target[7:] in NAMES,'Job is outside managed policy scope.')
        for vm in sorted(NAMES):jobs[vm]=drop_dependency_block(jobs[vm],target)
        vm=target[7:];j,p,s=paths(vm);oldp=p.read_text();newj=jobs[vm]
        require(re.search(r'Name\s*=\s*'+re.escape(target)+r'\s*$',newj,re.M),'Job ownership mismatch.')
        schedule_name='BC-Policy-'+vm
        payload=d if len(d['jobs'])==1 else {**d,'jobs':[target]}
        if payload['trigger_mode']=='calendar':
            if payload['calendar'] is None:
                active_name=re.search(r'^\s*Schedule\s*=\s*(\S+)',newj,re.M)
                active_text=(BASE/'schedule'/(active_name.group(1)+'.conf')).read_text() if active_name else ''
                require('# BackupCenter calendar:' not in active_text,'This job has a custom calendar. Edit its schedule from Jobs to preserve or change it explicitly.')
            newj=set_directive(newj,'Schedule',schedule_name)
            newj=set_directive(newj,'Reschedule On Error','yes' if payload['retry_count'] else 'no')
            newj=set_directive(newj,'Reschedule Times',str(payload['retry_count']) if payload['retry_count'] else None)
            newj=set_directive(newj,'Reschedule Interval',str(payload['retry_interval_minutes']*60) if payload['retry_count'] else None)
            newj=set_directive(newj,'Rerun Failed Levels','yes' if payload['retry_count'] else None)
            newj=set_marker(newj,payload);jobs[vm]=newj;schedules[vm]=calendar_schedule(schedule_name,payload['time_wita'],payload['automatic'],payload.get('calendar'),payload.get('window_end_wita'))
        else:
            source=payload['after_job']['source_job'];require(source.startswith('VMware-') and source[7:] in NAMES,'After-job source is outside managed scope.')
            newj=set_directive(newj,'Schedule',None)
            newj=set_directive(newj,'Reschedule On Error','yes' if payload['retry_count'] else 'no')
            newj=set_directive(newj,'Reschedule Times',str(payload['retry_count']) if payload['retry_count'] else None)
            newj=set_directive(newj,'Reschedule Interval',str(payload['retry_interval_minutes']*60) if payload['retry_count'] else None)
            newj=set_directive(newj,'Rerun Failed Levels','yes' if payload['retry_count'] else None)
            newj=set_marker(newj,payload);jobs[vm]=newj;schedules[vm]=None;jobs[source[7:]]=add_dependency_block(jobs[source[7:]],target,payload)
        newp,n=re.subn(r'(?m)^(\s*Volume Retention\s*=).*$',' Volume Retention = '+str(payload['retention_days'])+' days',oldp);require(n==1,'Expected one pool retention.')
        newp,n=re.subn(r'(?m)^(\s*Maximum Volumes\s*=).*$',' Maximum Volumes = '+str(payload['maximum_volumes']),newp);require(n==1,'Expected one pool volume limit.')
        require('AutoPrune = no' in newp and 'Recycle = yes' in newp,'Pool cleanup invariants changed.')
        changes.append({'path':str(p),'before':oldp,'after':newp});definitions[target]=payload
    ensure_cycle_free(definitions)
    for target,definition in definitions.items():verify_hooks(jobs,target,definition)
    for vm in sorted(NAMES):
        j,_,s=paths(vm)
        require(not j.is_symlink(),'Policy path cannot be a symlink.')
        if jobs[vm]!=j.read_text():changes.append({'path':str(j),'before':j.read_text(),'after':jobs[vm]})
        old=s.read_text() if s.exists() else None
        if schedules[vm]!=old:
            require(not s.is_symlink(),'Policy path cannot be a symlink.')
            changes.append({'path':str(s),'before':old,'after':schedules[vm]})
    retention_change=any(row['job'] in d['jobs'] and row['retentionDays']!=d['retention_days'] for row in observed['jobs'])
    old=RETIRE.read_text();new=patch_retention(old) if retention_change else old;compile(new,str(RETIRE),'exec');changes.append({'path':str(RETIRE),'before':old,'after':new})
    old=TRIGGER.read_text() if TRIGGER.exists() else None;new=trigger_script();compile(new,str(TRIGGER),'exec');changes.append({'path':str(TRIGGER),'before':old,'after':new})
    baseline=[{'path':c['path'],'beforeDigest':digest(c['before']) if c['before'] is not None else None,'afterDigest':digest(c['after']) if c['after'] is not None else None} for c in changes]
    value={'definition':d,'files':baseline};sha=digest(json.dumps(value,sort_keys=True,separators=(',',':')))
    return {'definition':d,'reviewDigest':sha,'changes':changes,'cadence':('After '+d['after_job']['source_job'] if d['trigger_mode']=='after_job' else (d['calendar'] or 'Full on 1 and 15; Incremental on other days')),'existingVolumePolicy':'Existing volume minima remain; cleanup uses the greater of Pool and Volume retention. Latest successful Full chain is preserved.','doesNotRun':'No backup, restore, prune or purge is executed by Apply.'}
def write(path,text):
    p=Path(path);fd,name=tempfile.mkstemp(prefix='.backupcenter-',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w') as stream:stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.chown(name,0,grp.getgrnam('bareos').gr_gid);os.chmod(name,0o750 if p in (RETIRE,TRIGGER) else 0o640);os.replace(name,p)
    finally:Path(name).unlink(missing_ok=True)
def active():
    p=subprocess.run(['runuser','-u','bareos','--','psql','-X','-At','-d','bareos','-c',"SELECT count(*) FROM job WHERE jobstatus IN ('R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L');"],text=True,capture_output=True,check=True)
    require(p.stdout.strip()=='0','Wait for active or waiting Bareos jobs to finish before applying policy.')
def syntax():
    p=subprocess.run(['runuser','-u','bareos','--','/opt/bareos/25.1.1/sbin/bareos-dir','-t'],text=True,capture_output=True,cwd='/var/lib/bareos',timeout=30)
    require(p.returncode==0,'Director validation failed; configuration will be rolled back.')
def verify(definition):
    observed=current()  # Exact on-disk hooks, cadence and retry read-back.
    for target in definition['jobs']:
        vm=target[7:];j,p,s=paths(vm)
        require(policy_marker(j.read_text())=={**definition,'jobs':[target]},'Policy marker differs from reviewed intent.')
    runtime=console('show jobs')['jobs']
    if definition['trigger_mode']=='calendar':require(all(runtime.get(job,{}).get('schedule')=='BC-Policy-'+job[7:] for job in definition['jobs']),'Director did not load the reviewed job schedules.')
    else:require(all(runtime.get(job,{}).get('schedule') in (None,'','Manual') for job in definition['jobs']),'Director did not clear the reviewed job schedule.')
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
            for c in p['changes']:
                if c['after'] is None:Path(c['path']).unlink(missing_ok=True)
                else:write(c['path'],c['after'])
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