#!/usr/bin/python3
"""Root-owned, UUID-scoped onboarding. No raw config, shell, power or delete API."""
import ast,configparser,fcntl,json,os,re,shutil,ssl,stat,subprocess,sys,time
from pathlib import Path
from uuid import UUID
sys.path.insert(0,'/opt/bareos-api')
sys.path.insert(0,'/opt/bareos/25.1.1/lib/bareos/vmware-python')
from onboarding_contract import build,POLICY
ROOT=Path('/etc/bareos');SCOPE=Path('/opt/bareos-api/backupcenter-onboarding-scope.json')
SCRIPT=Path('/opt/bareos/25.1.1/lib/bareos/scripts/prepare-vm-backup')
RETENTION=Path('/opt/bareos/25.1.1/lib/bareos/scripts/retire-vm-chains.py')
RECEIPTS=Path('/var/lib/bareos-onboarding');BIN='/opt/bareos/25.1.1/sbin/'
def cmd(args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=60,**kwargs).stdout
def secure(path):
    m=path.stat()
    if path.is_symlink() or m.st_uid!=0 or m.st_mode&0o022:raise ValueError('Administrator-owned scope/helper required')
def main(body):
    if os.geteuid()!=0:raise ValueError('Administrator helper required')
    if set(body)!={'vm_uuid','request_id','digest','policy'}:raise ValueError('Unexpected onboarding parameters')
    uid=str(UUID(body['vm_uuid']));rid=str(UUID(body['request_id']))
    if uid!=body['vm_uuid'] or rid!=body['request_id'] or body['policy']!=POLICY:raise ValueError('Invalid canonical identity or policy')
    secure(SCOPE);scope=json.loads(SCOPE.read_text());approval=scope.get('vms',{}).get(uid)
    if not approval:raise ValueError('VM is outside administrator-approved onboarding scope')
    plan=build(uid,approval['label'])
    if body['digest']!=plan['digest']:raise ValueError('Reviewed configuration digest changed')
    RECEIPTS.mkdir(mode=0o700,exist_ok=True)
    receipt=RECEIPTS/(rid+'.json')
    if receipt.exists():
        secure(receipt);result=json.loads(receipt.read_text())
        if result['vm_uuid']!=uid or result['digest']!=plan['digest']:raise ValueError('Request identity conflict')
        return result
    from pyVim.connect import Connect,Disconnect
    from pyVmomi import vim
    c=configparser.ConfigParser(interpolation=None);c.read('/etc/bareos/vmware-plugin.ini');o=c['vmware_plugin_options']
    si=Connect(host=o['vcserver'],user=o['vcuser'],pwd=o['vcpass'],thumbprint=o['vcthumbprint'],sslContext=ssl._create_unverified_context())
    saved={};created=[];folder=Path(plan['folder']);changed=False
    backup=RECEIPTS/(rid+'-rollback');backup.mkdir(mode=0o700,exist_ok=True)
    try:
        vm=si.content.searchIndex.FindByUuid(None,uid,True,True)
        if vm is None or vm.name!=approval['name']:raise ValueError('Approved VM identity/name changed')
        power=str(vm.runtime.powerState)
        if power!=approval['power'] or vm.snapshot or vm.runtime.consolidationNeeded:raise ValueError('Power/snapshot/consolidation changed; review required')
        if any(d.backing.diskMode!='persistent' for d in vm.config.hardware.device if isinstance(d,vim.vm.device.VirtualDisk)):raise ValueError('Unsupported disk mode')
        # Never enable CBT or create VMware snapshots here; the selected backup does that.
        cmd(['mountpoint','-q','/mnt/bareos-smb'])
        if cmd(['findmnt','-rn','-T','/mnt/bareos-smb','-o','FSTYPE']).strip()!='cifs':raise ValueError('SMB mount unavailable')
        if folder.is_symlink() or folder.resolve()!=Path('/mnt/bareos-smb')/approval['label']:raise ValueError('Invalid repository path')
        if folder.exists() and any(folder.iterdir()):raise ValueError('Existing repository requires reconciliation')
        for rel in plan['files']:
            if (ROOT/rel).exists():raise ValueError('Resource already exists; reconcile before retry')
        running=cmd(['runuser','-u','bareos','--','psql','-X','-At','-d','bareos','-c',"SELECT count(*) FROM job WHERE jobstatus IN ('R','C','B','F','S','M','s','m','j','c','d','t','p','q','a','i','L');"])
        if running.strip()!='0':raise ValueError('Wait until running backup jobs finish before storage reload')
        disks=sum(d.capacityInKB*1024 for d in vm.config.hardware.device if isinstance(d,vim.vm.device.VirtualDisk))
        space=os.statvfs('/mnt/bareos-smb')
        if space.f_bavail*space.f_frsize<disks*1.2:raise ValueError('Insufficient SMB free capacity')
        password=re.search(r'^\s*Password\s*=\s*(.+)$',(ROOT/'bareos-dir.d/storage/VeeamSMB.conf').read_text(),re.M)
        if not password:raise ValueError('Existing Storage secret unavailable')
        def write(p,text):
            nonlocal changed
            if p not in saved:
                if p.exists():
                    dest=backup/str(p).lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);saved[p]=dest
                else:created.append(p)
            tmp=p.with_name(p.name+'.onboarding-tmp');tmp.write_text(text);os.chmod(tmp,0o640 if str(p).startswith('/etc/') else 0o750);shutil.chown(tmp,'root','bareos');os.replace(tmp,p);changed=True
        shell=SCRIPT.read_text()
        if approval['label'] not in shell.split(') ;;')[0]:
            marker='MTIMRWCNTDEV) ;;'
            if shell.count(marker)!=1:raise ValueError('Preparation script baseline changed')
            shell=shell.replace(marker,'MTIMRWCNTDEV|'+approval['label']+') ;;',1)
        retention=RETENTION.read_text();match=re.search(r'^NAMES=(.+)$',retention,re.M)
        if not match:raise ValueError('Retention baseline changed')
        names=ast.literal_eval(match.group(1));names.add(approval['label'])
        retention=retention[:match.start(1)]+repr(names)+retention[match.end(1):]
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,59}',n) for n in names):raise ValueError('Unsafe retention mapping')
        # The original SQL only selects MTIMRW-prefixed pools/jobs; PNET needs explicit mappings too.
        pool_filter=','.join("'"+n+"'" for n in sorted(names))
        job_filter=','.join("'VMware-"+n+"'" for n in sorted(names))
        if "WHERE p.name LIKE 'MTIMRW%'" not in retention or "WHERE name LIKE 'VMware-MTIMRW%'" not in retention:raise ValueError('Retention query baseline changed; review required')
        retention=retention.replace("WHERE p.name LIKE 'MTIMRW%'",'WHERE p.name IN ('+pool_filter+')').replace("WHERE name LIKE 'VMware-MTIMRW%'",'WHERE name IN ('+job_filter+')')

        # All scripts and resources have exact root-owned destinations; no caller path is accepted.
        write(SCRIPT,shell);write(RETENTION,retention)
        for rel,text in plan['files'].items():write(ROOT/rel,text.replace('"<existing-storage-secret>"',password.group(1)))
        folder.mkdir(exist_ok=True);shutil.chown(folder,'bareos','bareos')
        cmd(['runuser','-u','bareos','--',BIN+'bareos-dir','-t']);cmd([BIN+'bareos-sd','-t']);cmd(['bash','-n',str(SCRIPT)])
        cmd(['systemctl','restart','bareos-storage']);cmd([BIN+'bconsole'],input='reload\nquit\n')
        cmd(['systemctl','is-active','bareos-storage','bareos-director'])
        result=cmd([BIN+'bconsole'],input='show job='+plan['job']+'\nquit\n')
        if 'Name = "'+plan['job']+'"' not in result:raise ValueError('Director load not confirmed')
        if str(vm.runtime.powerState)!=power:raise ValueError('VM power state changed externally; reconcile')
        result={'liveApplied':True,'simulationOnly':False,'vm_uuid':uid,'request_id':rid,'digest':plan['digest'],'job':plan['job'],'folder':plan['folder'],'power':power,'message':'Backup job configured. First backup is a separate confirmed action.'}
        receipt.write_text(json.dumps(result));os.chmod(receipt,0o600)
        return result
    except Exception:
        if changed:
            for p,q in saved.items():shutil.copy2(q,p)
            for p in created:p.unlink(missing_ok=True)
            try:cmd(['systemctl','restart','bareos-storage']);cmd([BIN+'bconsole'],input='reload\nquit\n')
            except Exception:raise RuntimeError('Apply failed; configuration rollback requires administrator verification')
        raise
    finally:Disconnect(si)
if __name__=='__main__':
    try:
        with open('/run/lock/backupcenter-onboarding.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            data=sys.stdin.buffer.read(8193)
            if len(data)>8192:raise ValueError('Request too large')
            print(json.dumps(main(json.loads(data))))
    except Exception as e:
        print(json.dumps({'error':str(e)}));sys.exit(1)
