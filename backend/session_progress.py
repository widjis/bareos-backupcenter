"""Observed restore progress only: no invented totals or percentages."""
from datetime import datetime,timezone
import re
TERMINAL={"T","W","A","E","e","f"}
def progress(row,lines,now=None):
    from backend.app import session
    s=session(row);active=row.get("jobstatus") not in TERMINAL
    text="\n".join(x['text'] for x in lines[-40:]).lower()
    if not active:phase={"T":"Completed","W":"Completed with warnings","A":"Canceled"}.get(row.get("jobstatus"),"Failed")
    elif 'successfully created vm' in text:phase="Restoring disks"
    elif 'creating vm' in text:phase="Creating destination VM"
    elif 'ready to read from volume' in text:phase="Reading backup volume"
    elif row.get('jobstatus')=='R':phase="Restore running"
    else:phase="Waiting for Bareos"
    def parse(value):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)
        except (ValueError,TypeError,AttributeError):return None
    start=parse(s['started']);end=parse(s['ended']) if not active else None
    clock=now or datetime.now(timezone.utc)
    elapsed=max(0,int(((end or clock)-start).total_seconds())) if start else None
    warnings=[]
    for line in lines:
        message=line['text']
        if 'warning:' not in message.lower():continue
        identity=bool(re.search(r'(mac address|uuid).*already exists.*generated',message,re.I|re.S))
        if identity:
            explanation="A new identity was generated for the restored copy because the source VM identity still exists."
        else:explanation="This warning needs review in the restore log."
        warnings.append({'kind':'identity-change' if identity else 'unclassified','explanation':explanation,'text':message})
    return {'warnings':warnings[-20:],'jobId':s['id'],'type':s['type'],'status':s['status'],'code':s['code'],'active':active,'phase':phase,'elapsedSeconds':elapsed,'bytes':s['bytes'],'files':s['files'],'errors':s['errors'],'percentage':None,'totalBytes':None,'counterSource':'Bareos Catalog; active-job counters may update only at completion','observedAt':clock.isoformat(),'lines':lines[-80:]}
