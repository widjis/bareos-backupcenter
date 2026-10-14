"""Install an additive read-only gateway extension with checksum/rollback guards."""
from pathlib import Path
from urllib.parse import urlparse
import json
import os
import subprocess
import shlex
from dotenv import dotenv_values
from backend.persistence import ROOT, Store

values=dotenv_values(ROOT/'.env')
if Store().operations():raise RuntimeError('Review real operation journal before API maintenance')
local=ROOT/'.local'
askpass=local/'bareos-askpass'
askpass.write_text('#!'+str(ROOT/'.venv/bin/python')+'\nfrom dotenv import dotenv_values\nprint(dotenv_values('+repr(str(ROOT/'.env'))+')["BAREOS_PASSWORD"])\n')
askpass.chmod(0o700)
known=local/'bareos-knownhosts'
if not known.exists():known.write_bytes(Path('/private/tmp/bareos-discovery-known-hosts').read_bytes())
endpoint=urlparse(values['BAREOS_HOST'] if '://' in values['BAREOS_HOST'] else '//'+values['BAREOS_HOST'])
env=os.environ.copy();env.update(SSH_ASKPASS=str(askpass),SSH_ASKPASS_REQUIRE='force',DISPLAY='backupcenter-extension')
program='''
import hashlib,json,os,py_compile,subprocess,sys,time,urllib.request
from pathlib import Path
payload=json.load(sys.stdin)
source=payload['source']
root=Path('/opt/bareos-api')
gateway=root/'gateway.py'
module=root/'backupcenter_extension.py'
original=gateway.read_text()
if 'from bareos_restapi import app' not in original or 'async def guard' not in original:
 raise RuntimeError('Unexpected gateway baseline')
backup=root/'gateway.py.before-backupcenter-recovery'
if not backup.exists():backup.write_text(original);backup.chmod(0o600)
prior=module.read_text() if module.exists() else None
restore_module=root/'backupcenter_restore.py'
prior_restore=restore_module.read_text() if restore_module.exists() else None
helper=root/'prepare_restore_target.py'
prior_helper=helper.read_text() if helper.exists() else None
try:
 helper.write_text(payload['helper']);helper.chmod(0o700)
 py_compile.compile(str(helper),doraise=True)
 module.write_text(source);module.chmod(0o644)
 restore_module=root/'backupcenter_restore.py'
 restore_module.write_text(payload['restore']);restore_module.chmod(0o644)
 py_compile.compile(str(restore_module),doraise=True)
 py_compile.compile(str(module),doraise=True)
 if 'import backupcenter_extension' not in original:gateway.write_text(original+'\\n# Additive typed read-only recovery inspection; existing guard remains authoritative.\\nimport backupcenter_extension\\n')
 if 'import backupcenter_restore' not in gateway.read_text():gateway.write_text(gateway.read_text()+'\\nimport backupcenter_restore\\n')
 py_compile.compile(str(gateway),doraise=True)
 subprocess.run(['systemctl','restart','bareos-restapi'],check=True)
 subprocess.run(['systemctl','is-active','--quiet','bareos-restapi'],check=True)
 for attempt in range(10):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=2) as response:
    if response.status==200:break
  except Exception:time.sleep(1)
 else:raise RuntimeError('REST API readiness failed')
 print('Typed recovery extensions installed; API readiness verified and configuration-write guard preserved.')
except Exception:
 gateway.write_text(original)
 if prior_helper is not None:helper.write_text(prior_helper);helper.chmod(0o700)
 elif helper.exists():helper.unlink()
 if prior is not None:module.write_text(prior)
 elif module.exists():module.unlink()
 if prior_restore is not None:restore_module.write_text(prior_restore)
 elif restore_module.exists():restore_module.unlink()
 subprocess.run(['systemctl','restart','bareos-restapi'])
 raise
'''
compile(program,'remote-installer','exec')
for filename in ('backupcenter_extension.py','backupcenter_restore.py','prepare_restore_target.py'):
    compile((ROOT/'integration'/filename).read_text(),filename,'exec')
args=['ssh','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),values['BAREOS_USERNAME']+'@'+endpoint.hostname,'sudo -S -p "" python3 -c '+shlex.quote(program)]
body=values['BAREOS_PASSWORD']+'\n'+json.dumps({'helper':(ROOT/'integration/prepare_restore_target.py').read_text(),'source':(ROOT/'integration/backupcenter_extension.py').read_text(),'restore':(ROOT/'integration/backupcenter_restore.py').read_text()})
result=subprocess.run(args,input=body.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=45)
if result.returncode:raise RuntimeError('Gateway extension install failed; inspect service using the server runbook')
print(result.stdout.decode())
