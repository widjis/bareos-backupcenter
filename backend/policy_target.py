"""Pinned one-shot transport for reviewed managed policy actions."""
import json,os,subprocess,tempfile,urllib.request
from pathlib import Path
from dotenv import dotenv_values
from backend.persistence import ROOT


# #region debug-point helpers
def _debug_active_policy(hypothesis_id, location, msg, data=None):
    _p = ROOT / ".dbg" / "active-policy-502.env"
    _u = "http://127.0.0.1:7777/event"
    _s = "active-policy-502"
    try:
        content = _p.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("DEBUG_SERVER_URL="):
                _u = line.split("=", 1)[1] or _u
            elif line.startswith("DEBUG_SESSION_ID="):
                _s = line.split("=", 1)[1] or _s
    except Exception:
        pass
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                _u,
                data=json.dumps(
                    {
                        "sessionId": _s,
                        "runId": "pre-fix",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "msg": msg,
                        "data": data or {},
                    }
                ).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=2,
        ).read()
    except Exception:
        pass
# #endregion

def invoke(body):
    values=dotenv_values(ROOT/'.env')
    # #region debug-point B:policy-target-entry
    _debug_active_policy("B","backend/policy_target.py:invoke","[DEBUG] Enter policy target invoke",{"action":body.get("action"),"platform":os.name,"host":values.get("BAREOS_HOST","")[:80]})
    # #endregion
    if os.name!='nt':
        # #region debug-point A:policy-target-platform-gate
        _debug_active_policy("A","backend/policy_target.py:invoke","[DEBUG] Policy target rejected current platform",{"action":body.get("action"),"platform":os.name})
        # #endregion
        raise ValueError('Managed policy transport is configured for this Windows environment.')
    host=values.get('BAREOS_HOST','').replace('https://','').replace('http://','').rstrip('/')
    if host!='10.60.10.77':
        # #region debug-point B:policy-target-host-gate
        _debug_active_policy("B","backend/policy_target.py:invoke","[DEBUG] Policy target rejected host",{"action":body.get("action"),"host":host})
        # #endregion
        raise ValueError('Unexpected policy gateway host.')
    fd,path=tempfile.mkstemp(suffix='.pw')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(values['BAREOS_PASSWORD'])
        args=[r'C:\Program Files\PuTTY\plink.exe','-batch','-ssh','-hostkey','SHA256:C+cwQRvFTgMM0RzwGrJYh7isR6lkfMQBpiwu+vbKu1I','-pwfile',path,values['BAREOS_USERNAME']+'@'+host,"sudo -S -p '' env PYTHONPATH=/opt/bareos/25.1.1/lib/bareos/vmware-python /opt/bareos-api-venv/bin/python /opt/bareos-api/apply_backup_policy.py"]
        result=subprocess.run(args,input=(values['BAREOS_PASSWORD']+'\n'+json.dumps(body)).encode(),capture_output=True,timeout=150)
        try:reply=json.loads(result.stdout)
        except Exception:raise RuntimeError('Policy gateway response unknown; reconcile before retrying.')
        if result.returncode:
            # #region debug-point B:policy-target-subprocess-failed
            _debug_active_policy("B","backend/policy_target.py:invoke","[DEBUG] Policy target subprocess failed",{"action":body.get("action"),"returncode":result.returncode,"stderr":result.stderr.decode(errors="ignore")[:250]})
            # #endregion
            message=str(reply.get('error','Policy gateway unavailable; reconcile receipt.'))[:250]
            if 'reconcile' in message:raise RuntimeError(message)
            raise ValueError(message)
        # #region debug-point D:policy-target-success
        _debug_active_policy("D","backend/policy_target.py:invoke","[DEBUG] Policy target returned successfully",{"action":body.get("action"),"replyState":reply.get("state"),"jobCount":len(reply.get("jobs",[])) if isinstance(reply.get("jobs"),list) else None})
        # #endregion
        return reply
    finally:Path(path).unlink(missing_ok=True)
