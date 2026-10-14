"""Typed one-shot SSH target preparation; invoked only after durable restore claim."""
import json
import os
import subprocess
from urllib.parse import urlparse
from uuid import UUID
from dotenv import dotenv_values
from backend.persistence import ROOT


def prepare_target(job_id,request_id):
    request=str(UUID(str(request_id)))
    if isinstance(job_id,bool) or not isinstance(job_id,int) or job_id<1:
        raise ValueError('Invalid source JobId.')
    values=dotenv_values(ROOT/'.env')
    if values.get('BACKUPCENTER_RESTORE_DISPATCH_ENABLED')!='1':
        raise ValueError('Live restore preparation is disabled.')
    host=urlparse(values['BAREOS_HOST'] if '://' in values['BAREOS_HOST'] else '//'+values['BAREOS_HOST']).hostname
    local=ROOT/'.local'
    environment=os.environ.copy()
    environment.update(SSH_ASKPASS=str(local/'bareos-askpass'),SSH_ASKPASS_REQUIRE='force',DISPLAY='backupcenter-restore')
    args=['ssh','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(local/'bareos-knownhosts'),values['BAREOS_USERNAME']+'@'+host,'sudo -S -p "" python3 /opt/bareos-api/prepare_restore_target.py']
    body=values['BAREOS_PASSWORD']+'\n'+json.dumps({'job_id':job_id,'request_id':request})
    result=subprocess.run(args,input=body.encode(),capture_output=True,env=environment,timeout=35)
    try:receipt=json.loads(result.stdout)
    except Exception:raise ValueError('Preparation outcome unconfirmed; reconcile before a new request.')
    if result.returncode or receipt.get('prepared') is not True or receipt.get('destination')!='/mnt/bareos-smb/backupcenter-restore-tests/'+request:
        raise ValueError('Preparation was not confirmed; no restore command was sent.')
