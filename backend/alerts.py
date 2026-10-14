"""Objective observed-session alerts; never infer RPO or recovery guarantees."""
from uuid import uuid5,NAMESPACE_URL
from psycopg2.extras import Json


def signals(snapshot):
    if snapshot.get("connection") not in ("connected","partial") or any(k in snapshot.get("sourceErrors",{}) for k in ("jobs","sessions")):
        return None
    configured={j["name"] for j in snapshot.get("jobs",[]) if j.get("type")=="Backup"}
    latest={}
    for session in snapshot.get("sessions",[]):
        if session.get("type")!="Backup" or session.get("name") not in configured or session.get("status") not in ("Succeeded","Warning","Failed","Canceled"):continue
        name=session["name"]
        if name not in latest or session["id"]>latest[name]["id"]:latest[name]=session
    return latest


def evaluate(cur,connection,snapshot):
    latest=signals(snapshot)
    if latest is None:return
    for name,session in latest.items():
        if session["status"] in ("Failed","Warning"):
            uid=str(uuid5(NAMESPACE_URL,connection+":session-alert:"+str(session["id"])))
            severity="Error" if session["status"]=="Failed" else "Warning"
            cur.execute("INSERT INTO session_alerts(id,connection_id,job_name,source_job_id,severity,evidence) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,source_job_id) DO UPDATE SET last_seen_at=now() RETURNING (xmax=0) AS created",(uid,connection,name,session["id"],severity,Json(session)))
            if cur.fetchone()[0]:cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,'local-collector','alert.opened',%s)",(connection,Json({"alertId":uid,"job":name,"sourceJobId":session["id"],"severity":severity})))
        elif session["status"]=="Succeeded":
            cur.execute("UPDATE session_alerts SET state='Resolved',resolved_by_job_id=%s,revision=revision+1,last_seen_at=now() WHERE connection_id=%s AND job_name=%s AND source_job_id<%s AND state<>'Resolved' RETURNING id",(session["id"],connection,name,session["id"]))
            for row in cur.fetchall():cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,'local-collector','alert.resolved',%s)",(connection,Json({"alertId":str(row[0]),"job":name,"resolvedByJobId":session["id"]})))
