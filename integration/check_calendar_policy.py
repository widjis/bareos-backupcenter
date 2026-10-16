"""Isolated helper checks: redirect all paths and mock native mutations."""
import sys,tempfile,types
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

def check():
 with tempfile.TemporaryDirectory(prefix='bc-calendar-check-') as folder:
  project=Path(__file__).resolve().parents[1]
  if str(project) not in sys.path:sys.path.insert(0,str(project))
  root=Path(folder);source=Path(__file__).with_name('apply_backup_policy.py').read_text().replace("'/var/lib/bareos/vm-chain-retention.lock'",repr(str(root/'lock')))
  sys.modules['fcntl']=types.SimpleNamespace(LOCK_EX=2,LOCK_NB=4,flock=lambda *args,**kwargs:None)
  sys.modules['grp']=types.SimpleNamespace(getgrnam=lambda name:types.SimpleNamespace(gr_gid=0))
  sys.modules['direct_vm_restore']=types.SimpleNamespace(console=lambda *args,**kwargs:{},require=lambda condition,message: (_ for _ in ()).throw(ValueError(message)) if not condition else None)
  sys.modules['active_policy_contract']=__import__('backend.active_policy',fromlist=['*'])
  m=types.ModuleType('fixture');m.__file__=str(Path(__file__).with_name('apply_backup_policy.py'));exec(compile(source,'fixture','exec'),m.__dict__)
  m.os.chown=lambda *args,**kwargs:None
  base=m.BASE;m.BASE=root/'config';m.ROOT=root/'receipts';m.RETIRE=root/'retire.py';m.TRIGGER=root/'backupcenter-after-job.py';m.RETIRE.write_text("import datetime\nTEMPLATE=\"\"\"\n cutoff=now-datetime.timedelta(days=30);jobs=\n  vm=m['pool'];name=m['volumename']\n m.lastwritten,m.poolid,p.name AS pool\n\"\"\"\n")
  for kind in ('job','pool','schedule'):(m.BASE/kind).mkdir(parents=True)
  (m.BASE/'schedule'/'VMwareTwiceMonthly.conf').write_text(m.schedule('VMwareTwiceMonthly','21:30',True))
  for vm in sorted(m.NAMES):
   (m.BASE/'job'/(vm+'.conf')).write_text('Job {\n Name = VMware-'+vm+'\n Schedule = VMwareTwiceMonthly\n Pool = '+vm+'\n}\n')
   (m.BASE/'pool'/(vm+'.conf')).write_text('Pool {\n Name = '+vm+'\n Volume Retention = 30 days\n Maximum Volumes = 6\n AutoPrune = no\n Recycle = yes\n}\n')
  before={p:p.read_bytes() for p in m.BASE.rglob('*.conf')}
  d=dict(jobs=['VMware-PNET'],time_wita='22:15',retention_days=30,maximum_volumes=8,automatic=True,calendar=dict(mode='weekly',weekdays=[1,3,5],full_mode='weekly',full_weekday=5))
  plan=m.plan(d)
  retirement=next(c for c in plan['changes'] if c['path']==str(m.RETIRE));assert retirement['before']==retirement['after'],'Schedule-only review must not migrate global cleanup code'
  retention=m.plan({**d,'retention_days':45,'maximum_volumes':10})
  retirement=next(c for c in retention['changes'] if c['path']==str(m.RETIRE));assert retirement['before']!=retirement['after'] and 'poolretention' in retirement['after'],'Explicit retention change must include reviewed Pool-aware migration'
  body=dict(definition=d,request_id=str(uuid4()),digest=plan['reviewDigest'],actor='fixture')
  def verify(definition):
   row=next(r for r in m.current()['jobs'] if r['job']=='VMware-PNET')
   assert row['calendar']['weekdays']==[1,3,5] and row['timeWita']=='22:15'
  with patch.object(m,'console',return_value={}),patch.object(m,'active'),patch.object(m,'syntax'),patch.object(m,'verify',side_effect=verify):
   result=m.apply(body);assert result['state']=='Applied';assert m.apply(body)==result
  assert 'Max Run Sched Time' not in (m.BASE/'job'/'PNET.conf').read_text()
  for p,raw in before.items():
   if p.name!='PNET.conf':assert p.read_bytes()==raw,'Unselected resource changed'
  try:m.plan({k:v for k,v in d.items() if k!='calendar'})
  except ValueError as e:assert 'custom calendar' in str(e)
  else:raise AssertionError('Legacy overwrite accepted')
  after=dict(jobs=['VMware-PNET'],time_wita='22:15',retention_days=30,maximum_volumes=8,automatic=True,trigger_mode='after_job',calendar=None,after_job=dict(source_job='VMware-MTIMRWKF01',on_failure='run_anyway',level='incremental'),window_end_wita='23:30',retry_count=2,retry_interval_minutes=45)
  plan=m.plan(after);body=dict(definition=after,request_id=str(uuid4()),digest=plan['reviewDigest'],actor='fixture')
  def verify_after(definition):
   row=next(r for r in m.current()['jobs'] if r['job']=='VMware-PNET')
   assert row['triggerMode']=='after_job' and row['afterJob']['source_job']=='VMware-MTIMRWKF01'
  with patch.object(m,'console',return_value={'jobs':{'VMware-PNET':{'schedule':'Manual'}}}),patch.object(m,'active'),patch.object(m,'syntax'),patch.object(m,'verify',side_effect=verify_after):
   result=m.apply(body);assert result['state']=='Applied'
  source_text=(m.BASE/'job'/'MTIMRWKF01.conf').read_text()
  assert 'Run After Job = "/opt/bareos-api-venv/bin/python '+str(m.TRIGGER)+' --source VMware-MTIMRWKF01 --source-job-id %i --target VMware-PNET --level incremental --window-start 22:15 --window-end 23:30"' in source_text
  assert 'Run After Failed Job = "/opt/bareos-api-venv/bin/python '+str(m.TRIGGER)+' --source VMware-MTIMRWKF01 --source-job-id %i --target VMware-PNET --level incremental --window-start 22:15 --window-end 23:30"' in source_text
  target_text=(m.BASE/'job'/'PNET.conf').read_text()
  assert ' Reschedule On Error = yes' in target_text
  assert ' Reschedule Times = 2' in target_text
  assert ' Reschedule Interval = 2700' in target_text
  assert ' Rerun Failed Levels = yes' in target_text
  assert 'Max Run Sched Time' not in target_text
  assert (m.BASE/'schedule'/'BC-Policy-PNET.conf').exists() is False
  assert m.TRIGGER.exists()
  assert m.TRIGGER.read_text()==Path(__file__).with_name('after_job_runtime.py').read_text()
  import json
  with patch.object(m,'console',return_value={'jobs':{'VMware-PNET':{'schedule':'Manual'}}}),patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(stdout=json.dumps([{'retention':30*86400,'maximum':8}]))):
   m.verify(m.ActivePolicy(**after).model_dump())
  other=m.BASE/'job'/'MTIMRWCNTDEV.conf';old_other=other.read_text()
  other.write_text(old_other+'\n'+m.dependency_block('VMware-PNET',m.ActivePolicy(**after).model_dump()))
  try:m.current()
  except ValueError:pass
  else:raise AssertionError('Stale duplicate source hook accepted')
  other.write_text(old_other)
  target=m.BASE/'job'/'PNET.conf';old_target=target.read_text();target.write_text(old_target.replace(' Reschedule Times = 2',' Reschedule Times = 9'))
  try:m.current()
  except ValueError:pass
  else:raise AssertionError('Retry directive drift accepted')
  target.write_text(old_target)
  before={p:p.read_bytes() for p in m.BASE.rglob('*.conf')};d={**d,'time_wita':'23:00'};plan=m.plan(d)
  with patch.object(m,'console',return_value={}),patch.object(m,'active'),patch.object(m,'syntax'),patch.object(m,'verify',side_effect=ValueError('mocked verification failure')):
   assert m.apply(dict(definition=d,request_id=str(uuid4()),digest=plan['reviewDigest'],actor='fixture'))['state']=='Failed'
  assert all(p.read_bytes()==raw for p,raw in before.items())
  print('Isolated helper: exact-job apply, after-job dependency, read-back, replay, retry directives, unselected resources, custom-overwrite rejection and rollback passed. Native mutations mocked; production files unchanged.')
if __name__=='__main__':check()
