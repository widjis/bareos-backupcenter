"""Pinned one-shot transport for reviewed managed policy actions."""
import json,os,subprocess,tempfile
from pathlib import Path
from dotenv import dotenv_values
from backend.persistence import ROOT

def invoke(body):
    values=dotenv_values(ROOT/'.env')
    if os.name!='nt':raise ValueError('Managed policy transport is configured for this Windows environment.')
    host=values.get('BAREOS_HOST','').replace('https://','').replace('http://','').rstrip('/')
    if host!='10.60.10.77':raise ValueError('Unexpected policy gateway host.')
    fd,path=tempfile.mkstemp(suffix='.pw')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(values['BAREOS_PASSWORD'])
        args=[r'C:\Program Files\PuTTY\plink.exe','-batch','-ssh','-hostkey','SHA256:C+cwQRvFTgMM0RzwGrJYh7isR6lkfMQBpiwu+vbKu1I','-pwfile',path,values['BAREOS_USERNAME']+'@'+host,"sudo -S -p '' env PYTHONPATH=/opt/bareos/25.1.1/lib/bareos/vmware-python /opt/bareos-api-venv/bin/python /opt/bareos-api/apply_backup_policy.py"]
        result=subprocess.run(args,input=(values['BAREOS_PASSWORD']+'\n'+json.dumps(body)).encode(),capture_output=True,timeout=150)
        try:reply=json.loads(result.stdout)
        except Exception:raise RuntimeError('Policy gateway response unknown; reconcile before retrying.')
        if result.returncode:
            message=str(reply.get('error','Policy gateway unavailable; reconcile receipt.'))[:250]
            if 'reconcile' in message:raise RuntimeError(message)
            raise ValueError(message)
        return reply
    finally:Path(path).unlink(missing_ok=True)
