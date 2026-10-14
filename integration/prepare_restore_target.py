"""Root-only typed preparation of one approved fresh restore target.
Installation does not enable or execute target preparation.
"""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from uuid import UUID

ROOT=Path('/mnt/bareos-smb/backupcenter-restore-tests')
SCOPE=Path('/opt/bareos-api/backupcenter-restore-scope.json')
RECEIPTS=Path('/opt/bareos-api/restore-preparations')


def rpc_objects(text):
    decoder=json.JSONDecoder();index=0;result=[]
    while index<len(text):
        start=text.find('{',index)
        if start<0:break
        try:obj,size=decoder.raw_decode(text[start:]);index=start+size
        except ValueError:index=start+1;continue
        if isinstance(obj,dict) and obj.get('jsonrpc')=='2.0':result.append(obj)
    return result


def prepare(body):
    if os.geteuid()!=0:raise ValueError('Target preparation requires administrator service ownership.')
    if set(body)!={'job_id','request_id'}:raise ValueError('Unexpected preparation parameters.')
    job_id=body['job_id'];request=UUID(str(body['request_id']))
    if str(request)!=body['request_id']:raise ValueError('Request UUID must be canonical.')
    if not isinstance(job_id,int) or isinstance(job_id,bool) or not 0<job_id<=9223372036854775807:raise ValueError('Invalid backup JobId.')
    if not SCOPE.exists() or SCOPE.is_symlink():raise ValueError('Restore test scope is not enabled.')
    flag=SCOPE.stat()
    if flag.st_uid!=0 or flag.st_mode & (stat.S_IWGRP|stat.S_IWOTH):raise ValueError('Restore scope permissions are invalid.')
    allowed=json.loads(SCOPE.read_text()).get('jobs',[])
    response=subprocess.run(['/opt/bareos/25.1.1/sbin/bconsole'],input='.api 2\nllist jobid='+str(job_id)+'\nquit\n',text=True,capture_output=True,timeout=20)
    objects=rpc_objects(response.stdout)
    rows=next((o['result']['jobs'] for o in objects if 'jobs' in o.get('result',{})),[])
    if response.returncode or len(rows)!=1:raise ValueError('Catalog source is unavailable.')
    source=rows[0]
    if str(source.get('jobid'))!=str(job_id) or source.get('name') not in allowed or source.get('type')!='B' or source.get('jobstatus') not in ('T','W'):raise ValueError('Backup source is outside the approved test scope.')
    mount=Path('/mnt/bareos-smb')
    entries=[line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    if not any(len(f)>6 and f[4]==str(mount) and '-' in f and f[f.index('-')+1]=='cifs' for f in entries):raise ValueError('Expected CIFS repository is unavailable.')
    if mount.is_symlink() or not os.path.ismount(mount):raise ValueError('Repository identity is invalid.')
    if ROOT.exists() and ROOT.is_symlink():raise ValueError('Restore root cannot be a symbolic link.')
    ROOT.mkdir(mode=0o770,exist_ok=True)
    if ROOT.resolve()!=ROOT:raise ValueError('Restore root identity changed.')
    destination=ROOT/str(request)
    destination.mkdir(mode=0o770,exist_ok=False)
    account=pwd.getpwnam('bareos')
    os.chown(destination,account.pw_uid,account.pw_gid)
    metadata=destination.stat()
    api_group=pwd.getpwnam('bareos-api').pw_gid
    if RECEIPTS.exists():
        directory=RECEIPTS.lstat()
        if not stat.S_ISDIR(directory.st_mode) or directory.st_uid!=0 or directory.st_mode & 0o022:
            raise ValueError('Receipt directory ownership is invalid.')
    RECEIPTS.mkdir(mode=0o750,exist_ok=True)
    os.chown(RECEIPTS,0,api_group)
    receipt={'requestId':str(request),'sourceJobId':job_id,'job':source['name'],'destination':str(destination),'device':metadata.st_dev,'inode':metadata.st_ino,'prepared':True}
    path=RECEIPTS/(str(request)+'.json')
    with path.open('x') as file:json.dump(receipt,file)
    path.chmod(0o640);os.chown(path,0,api_group)
    return {'prepared':True,'destination':str(destination)}


if __name__=='__main__':
    try:print(json.dumps(prepare(json.load(sys.stdin))))
    except Exception:print(json.dumps({'prepared':False,'error':'Approved fresh restore target preparation failed; no restore command was sent.'}));sys.exit(1)
