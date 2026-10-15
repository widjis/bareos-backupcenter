"""Typed Windows SSH transport for root-scoped onboarding; never sends raw config."""
import json,os,subprocess,tempfile
from pathlib import Path
from uuid import UUID
from dotenv import dotenv_values
from backend.persistence import ROOT
from integration.onboarding_contract import POLICY
class OnboardingUnknown(RuntimeError):pass
def apply_target(plan,request_id):
    values=dotenv_values(ROOT/'.env')
    changes=plan.get('changes',[])
    approved={x.strip() for x in values.get('BACKUPCENTER_ONBOARDING_UUIDS','').split(',') if x.strip()}
    if values.get('BACKUPCENTER_ONBOARDING_ENABLED')!='1' or len(changes)!=1 or changes[0].get('instanceUuid') not in approved:raise ValueError('Live onboarding is outside the approved VM scope')
    if os.name!='nt':raise ValueError('Controlled onboarding SSH transport is configured for this Windows pilot only')
    host=values.get('BAREOS_HOST','').replace('https://','').replace('http://','').rstrip('/')
    if host!='10.60.10.77':raise ValueError('Unexpected onboarding host')
    row=changes[0];rid=str(UUID(str(request_id)))
    body={'vm_uuid':row['instanceUuid'],'request_id':rid,'digest':plan['configurationDigest'],'policy':POLICY}
    fd,path=tempfile.mkstemp(suffix='.pw')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(values['BAREOS_PASSWORD'])
        args=[r'C:\Program Files\PuTTY\plink.exe','-batch','-ssh','-hostkey','SHA256:C+cwQRvFTgMM0RzwGrJYh7isR6lkfMQBpiwu+vbKu1I','-pwfile',path,values['BAREOS_USERNAME']+'@'+host,"sudo -S -p '' /opt/bareos-api-venv/bin/python /opt/bareos-api/apply_onboarding.py"]
        try:result=subprocess.run(args,input=(values['BAREOS_PASSWORD']+'\n'+json.dumps(body)).encode(),capture_output=True,timeout=150)
        except (subprocess.TimeoutExpired,OSError):raise OnboardingUnknown('Onboarding delivery outcome unknown; inspect the root receipt before retrying')
        try:reply=json.loads(result.stdout)
        except Exception:raise OnboardingUnknown('Onboarding receipt unavailable; do not resend')
        if result.returncode:raise ValueError('Controlled onboarding rejected: '+str(reply.get('error','administrator review required'))[:200])
        if not (reply.get('liveApplied') is True and reply.get('vm_uuid')==row['instanceUuid'] and reply.get('request_id')==rid and reply.get('digest')==plan['configurationDigest'] and reply.get('job')==row['job']):raise OnboardingUnknown('Onboarding receipt mismatch; administrator reconciliation required')
        return reply
    finally:Path(path).unlink(missing_ok=True)
