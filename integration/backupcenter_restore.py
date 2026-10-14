"""Isolated VMware disk export only; disabled unless root approves a job scope."""
from pathlib import Path
import json
import os
import re
import stat
from uuid import UUID
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from bareos_restapi import app, get_current_user
from backupcenter_extension import call, recovery

ROOT = Path('/mnt/bareos-smb/backupcenter-restore-tests')
APPROVAL = Path('/opt/bareos-api/backupcenter-restore-scope.json')


class ExportRequest(BaseModel):
    job_id: int
    request_id: UUID
    confirmed: bool
    model_config=ConfigDict(extra='forbid')


def safe_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value):
        raise HTTPException(409,'Resource name is not supported by isolated restore.')
    return value


def export_plan(job_id, request_id, user):
    info=recovery(job_id,user)
    if any(str(j.get('purgedfiles'))!='0' or not j.get('media') or j.get('mediaMappingsTruncated') for j in info['chain']):
        raise HTTPException(409,'Recovery requires complete file and media metadata.')
    if not any(j['level']=='F' for j in info['chain']):
        raise HTTPException(409,'A Full backup baseline is required.')
    for member in info['jobIds']:
        filenames=call(user,'list files jobid='+str(member)).get('filenames',[])
        if not filenames or len(filenames)>2000:raise HTTPException(409,'Bounded VMware file metadata is required.')
        for row in filenames:
            filename=str(row.get('filename',''))
            if not filename.startswith('/VMS/') or '\x00' in filename or '..' in Path(filename).parts:
                raise HTTPException(409,'Unexpected VMware backup path; isolated restore requires review.')
    source=next(j for j in info['chain'] if int(j['jobid'])==job_id)
    name=safe_name(source['name'])
    jobs=call(user,'show jobs').get('jobs',{})
    definition=jobs.get(name,{})
    client=safe_name(definition.get('client'))
    fileset_name=safe_name(definition.get('fileset'))
    filesets=call(user,'show filesets').get('filesets',{})
    plugins=' '.join(str(v) for inc in filesets.get(fileset_name,{}).get('include',[]) for v in inc.get('plugin',[]))
    if 'bareos-fd-vmware' not in plugins:raise HTTPException(409,'Only VMware plugin sources are eligible.')
    clients=call(user,'list clients').get('clients',[])
    if not any(c.get('name')==client and str(c.get('clientid'))==str(source['clientid']) for c in clients):
        raise HTTPException(409,'Source client no longer matches configuration.')
    restore=jobs.get('RestoreFiles',{})
    if restore.get('type')!='Restore':raise HTTPException(409,'Expected RestoreFiles template is unavailable.')
    storages=definition.get('storage',[])
    if isinstance(storages,str):storages=[storages]
    if len(storages)!=1:raise HTTPException(409,'An unambiguous source Storage is required.')
    storage=safe_name(storages[0])
    target=str(ROOT/str(request_id))
    # All command tokens are fixed, validated names, canonical numeric IDs, or UUID paths.
    command=('restore jobid='+','.join(str(x) for x in info['jobIds'])+' client='+client+' restoreclient='+client+' restorejob=RestoreFiles storage='+storage+' where='+target+' replace=never pluginoptions=python:module_name=bareos-fd-vmware:localvmdk=yes comment=backupcenter-'+str(request_id)+' select all done yes')
    return {'sourceJobId':job_id,'job':name,'jobIds':info['jobIds'],'destination':target,'overwrite':'Never','mode':'vm-disks-isolated','command':command}


RECEIPTS=Path('/opt/bareos-api/restore-preparations')


def validate_receipt(plan,job_id,request_id):
    # Preparation is performed by the narrow root helper; this API never writes the share.
    receipt_path=RECEIPTS/(str(request_id)+'.json')
    try:
        parent=receipt_path.parent
        if parent.is_symlink() or parent.stat().st_uid!=0 or parent.stat().st_mode & 0o022:
            raise ValueError()
        descriptor=os.open(receipt_path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(descriptor) as stream:
            metadata=os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=0 or metadata.st_mode & 0o022 or metadata.st_size>4096:
                raise ValueError()
            receipt=json.load(stream)
        if receipt.get('prepared') is not True or receipt.get('requestId')!=str(request_id) or receipt.get('sourceJobId')!=job_id or receipt.get('job')!=plan['job'] or receipt.get('destination')!=plan['destination']:
            raise ValueError()
    except Exception:
        raise HTTPException(409,'A matching administrator-owned preparation receipt is required; no job was sent.')


@app.post('/backupcenter/restore/vm-disks',tags=['backupcenter-recovery'])
def export_disks(body:ExportRequest,current_user=Depends(get_current_user)):
    if body.job_id<1 or body.job_id>9223372036854775807 or body.confirmed is not True:
        raise HTTPException(422,'An explicitly confirmed backup JobId is required.')
    # The flag is root-owned and cannot be enabled via this service or browser.
    try:approved=APPROVAL.exists()
    except PermissionError:raise HTTPException(403,'Restore scope is inaccessible; no job was sent.')
    if not approved:raise HTTPException(403,'Live isolated restore has not been enabled by the server administrator.')
    metadata=APPROVAL.stat()
    if APPROVAL.is_symlink() or metadata.st_uid!=0 or metadata.st_mode & (stat.S_IWGRP|stat.S_IWOTH):
        raise HTTPException(403,'Restore scope file permissions are invalid.')
    try:allowed=json.loads(APPROVAL.read_text()).get('jobs',[])
    except Exception:raise HTTPException(403,'Restore scope file is invalid.')
    plan=export_plan(body.job_id,body.request_id,current_user)
    if plan['job'] not in allowed:raise HTTPException(403,'Source job is outside the administrator-approved restore scope.')
    validate_receipt(plan,body.job_id,body.request_id)
    # Once this call starts, any transport failure is an unknown outcome; never retry.
    try:
        result=current_user.jsonDirector.call(plan['command'])
        job_id=int(result['run']['jobid'])
        if job_id<1:raise ValueError()
        return {'jobid':job_id,'destination':plan['destination']}
    except Exception:
        raise HTTPException(500,'Restore delivery outcome unknown; inspect Director history. Do not resend.')


@app.get('/backupcenter/restore/plan/{job_id}',tags=['backupcenter-recovery'])
def inspect_export_plan(job_id:int,request_id:UUID,current_user=Depends(get_current_user)):
    if job_id<1 or job_id>9223372036854775807:raise HTTPException(422,'Invalid backup JobId.')
    plan=export_plan(job_id,request_id,current_user)
    plan.pop('command',None)
    plan['destinationPermissionsVerified']=False
    plan['restoreVerified']=False
    return plan
