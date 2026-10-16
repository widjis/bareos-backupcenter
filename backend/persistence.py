"""Application-owned PostgreSQL persistence; never uses the Bareos Catalog."""
import copy
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

import psycopg2
from psycopg2.extras import Json, RealDictCursor
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self):
        values = dotenv_values(ROOT / ".env")
        self.configured = bool(values.get("BACKUPCENTER_DB_NAME"))
        self.connection_id = str(uuid5(NAMESPACE_URL, values.get("BAREOS_API_BASE_URL", "")))
        self.kwargs = {
            "host": values.get("BACKUPCENTER_DB_HOST"),
            "port": values.get("BACKUPCENTER_DB_PORT", "5432"),
            "dbname": values.get("BACKUPCENTER_DB_NAME"),
            "user": values.get("BACKUPCENTER_DB_USER"),
            "password": values.get("BACKUPCENTER_DB_PASSWORD"),
            "sslmode": values.get("BACKUPCENTER_DB_SSLMODE", "require"),
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000 -c search_path=backupcenter,pg_catalog",
            "application_name": "backupcenter-monitoring",
        }
        if values.get("BACKUPCENTER_DB_SSLROOTCERT"):
            self.kwargs["sslrootcert"] = values["BACKUPCENTER_DB_SSLROOTCERT"]

    def connect(self):
        if not self.configured:
            raise RuntimeError("Application database not configured")
        return psycopg2.connect(**self.kwargs)

    def load(self):
        with closing(self.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT payload FROM latest_snapshots WHERE connection_id=%s", (self.connection_id,))
                row = cur.fetchone()
                return copy.deepcopy(row[0]) if row else None

    def save(self, snapshot):
        # Persist only the normalized DTO, never raw Bareos configuration or credentials.
        clean = copy.deepcopy(snapshot)
        clean.pop("persistence", None)
        cid = self.connection_id
        with closing(self.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO connections(id,name,provider) VALUES(%s,%s,'bareos') ON CONFLICT(id) DO UPDATE SET name=excluded.name,last_seen_at=now()", (cid, clean["director"]["name"]))
                cur.execute("INSERT INTO latest_snapshots(connection_id,payload,synced_at) VALUES(%s,%s,%s) ON CONFLICT(connection_id) DO UPDATE SET payload=excluded.payload,synced_at=excluded.synced_at,persisted_at=now()", (cid, Json(clean), clean["syncedAt"]))
                if "jobs" not in clean["sourceErrors"] and "filesets" not in clean["sourceErrors"]:
                    cur.execute("UPDATE workloads SET configured=false WHERE connection_id=%s", (cid,))
                    for workload in clean["workloads"]:
                        wid = str(uuid5(NAMESPACE_URL, cid + ":" + workload["job"]))
                        cur.execute("INSERT INTO workloads(id,connection_id,job_name,display_name,proxy_name,folder_path) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,job_name) DO UPDATE SET display_name=excluded.display_name,proxy_name=excluded.proxy_name,folder_path=excluded.folder_path,configured=true,last_seen_at=now()", (wid,cid,workload["job"],workload["name"],workload["proxy"],workload["folder"]))
                for session in clean["sessions"]:
                    cur.execute("INSERT INTO session_observations(connection_id,job_id,payload) VALUES(%s,%s,%s) ON CONFLICT(connection_id,job_id) DO UPDATE SET payload=excluded.payload,last_seen_at=now()", (cid, session["id"], Json(session)))
                from backend.alerts import evaluate
                evaluate(cur,cid,clean)
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,'local-collector','snapshot.persisted',%s)", (cid, Json({"workloads":len(clean["workloads"]),"sessions":len(clean["sessions"]),"connection":clean["connection"]})))

    def status(self):
        with closing(self.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT (SELECT count(*) FROM workloads WHERE connection_id=%s), (SELECT count(*) FROM session_observations WHERE connection_id=%s), (SELECT count(*) FROM audit_events WHERE connection_id=%s)", (self.connection_id,)*3)
                workloads,sessions,events=cur.fetchone()
                cur.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
                ssl=cur.fetchone()
                return {"state":"connected","database":"backupcenter","workloads":workloads,"sessions":sessions,"auditEvents":events,"encrypted":bool(ssl and ssl[0]),"certificateValidated":self.kwargs["sslmode"] in ("verify-ca","verify-full")}

    def audit(self, limit=100):
        with closing(self.connect()) as conn:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id,actor,event_type,details,created_at FROM audit_events WHERE connection_id=%s OR connection_id IS NULL ORDER BY id DESC LIMIT %s", (self.connection_id,limit))
                return [dict(row) for row in cur.fetchall()]

    def operations(self, pending=False):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s " + ("AND (state IN ('Prepared','Accepted','Running') OR (state='Unknown' AND job_id IS NOT NULL)) " if pending else "") + ("ORDER BY CASE WHEN state='Prepared' THEN 0 ELSE 1 END, created_at ASC LIMIT 20" if pending else "ORDER BY created_at DESC LIMIT 100"), (self.connection_id,))
                return [dict(row) for row in cur.fetchall()]

    def operation(self, operation_id):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s AND id=%s",(self.connection_id,str(operation_id)))
                row=cur.fetchone()
                return dict(row) if row else None

    @staticmethod
    def operation_audit(cur, row):
        cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,%s,%s)", (row["connection_id"],row["actor"],"operation."+row["state"].lower(),Json({"operationId":str(row["id"]),"kind":row["kind"],"target":row["target"],"jobId":row["job_id"],"state":row["state"]})))

    def prepare(self, kind, target, key, actor, parameters=None):
        from uuid import uuid4
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":key:"+str(key),))
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":"+kind+":"+target,))
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s AND idempotency_key=%s",(self.connection_id,str(key)))
                existing=cur.fetchone()
                if existing:
                    if existing["kind"]!=kind or existing["target"]!=target:
                        raise ValueError("Idempotency key belongs to a different request")
                    if kind=="run" and existing["parameters"].get("requestedLevel")!=(parameters or {}).get("requestedLevel"):
                        raise ValueError("Idempotency key belongs to a different backup level")
                    return dict(existing)
                cur.execute("SELECT id FROM operation_requests WHERE connection_id=%s AND kind=%s AND target=%s AND state IN ('Prepared','Dispatching','Accepted','Running','Unknown')",(self.connection_id,kind,target))
                active=cur.fetchone()
                if active:
                    raise ValueError("An unresolved operation already exists for this target")
                cur.execute("INSERT INTO connections(id,name,provider) VALUES(%s,'Bareos Director','bareos') ON CONFLICT(id) DO NOTHING",(self.connection_id,))
                cur.execute("INSERT INTO operation_requests(id,connection_id,idempotency_key,kind,target,state,actor,job_id,parameters) VALUES(%s,%s,%s,%s,%s,'Prepared',%s,%s,%s) RETURNING *",(str(uuid4()),self.connection_id,str(key),kind,target,actor,int(target) if kind=="cancel" else None,Json(parameters if parameters is not None else ({"mode":"vm-disks-isolated","overwrite":"Never","destination":"/mnt/bareos-smb/backupcenter-restore-tests/"+str(key)} if kind=="restore" else {}))))
                row=dict(cur.fetchone())
                self.operation_audit(cur,row)
                return row

    def transition(self, operation_id, expected, state, job_id=None, message="", session_status=None):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                if state=="Dispatching":
                    cur.execute("SELECT actor,kind FROM operation_requests WHERE connection_id=%s AND id=%s AND state=ANY(%s) FOR UPDATE",(self.connection_id,str(operation_id),expected))
                    request=cur.fetchone()
                    if not request:return None
                    # Coordinate with account edits: authorization is held through the claim commit.
                    cur.execute("SELECT enabled,role FROM app_users WHERE username=%s FOR SHARE",(request["actor"],))
                    user=cur.fetchone()
                    allowed=user and user["enabled"] and (user["role"]=="Admin" or (user["role"]=="Backup Operator" and request["kind"] in ("run","cancel")))
                    if not allowed:
                        cur.execute("UPDATE operation_requests SET state='Failed',parameters=parameters || %s,updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",(Json({"message":"Permission was revoked before dispatch; no command was sent."}),self.connection_id,str(operation_id)))
                        self.operation_audit(cur,dict(cur.fetchone()))
                        return None
                detail={"message":message}
                if session_status:detail["sessionStatus"]=session_status
                cur.execute("UPDATE operation_requests SET state=%s,job_id=COALESCE(%s,job_id),parameters=parameters || %s,updated_at=now() WHERE connection_id=%s AND id=%s AND state=ANY(%s) RETURNING *",(state,job_id,Json(detail),self.connection_id,str(operation_id),expected))
                row=cur.fetchone()
                if row:
                    row=dict(row)
                    self.operation_audit(cur,row)
                    return row
                return None

    def recover_dispatching(self):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("UPDATE operation_requests SET state='Unknown',parameters=parameters || %s,updated_at=now() WHERE connection_id=%s AND state='Dispatching' RETURNING *",(Json({"message":"Backend interrupted during dispatch. Check Bareos history; this command will not be resent."}),self.connection_id))
                for row in cur.fetchall():self.operation_audit(cur,dict(row))

    def worker_lock(self):
        connection=self.connect()
        connection.autocommit=True
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))",("backupcenter-worker:"+self.connection_id,))
                if cur.fetchone()[0]:return connection
        except Exception:
            connection.close()
            raise
        connection.close()
        return None

    def operation_key(self, key):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s AND idempotency_key=%s",(self.connection_id,str(key)))
                row=cur.fetchone()
                return dict(row) if row else None

    def assignment_map(self):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT inventory_vm_id,job_name,state FROM protection_assignments WHERE connection_id=%s AND state<>'Retired'",(self.connection_id,))
                return {str(row["inventory_vm_id"]):dict(row) for row in cur.fetchall()}

    def assignment_detail(self, job_name):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT inventory_vm_id,instance_uuid,configuration_revision_id,policy_id,policy_revision,job_name,fileset_name,pool_name,storage_name,state FROM protection_assignments WHERE connection_id=%s AND job_name=%s AND state<>'Retired' ORDER BY updated_at DESC LIMIT 2",(self.connection_id,job_name))
                rows=[dict(row) for row in cur.fetchall()]
                if len(rows)>1:raise ValueError("Managed job has multiple active persisted assignments.")
                return rows[0] if rows else None

    def latest_lifecycle_revision(self, job_name):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM configuration_revisions WHERE connection_id=%s AND payload->>'kind'='lifecycle' AND payload->>'jobName'=%s ORDER BY updated_at DESC,created_at DESC LIMIT 1",(self.connection_id,job_name))
                row=cur.fetchone()
                return dict(row) if row else None

    def lifecycle_operations(self, job_name):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id,kind,target,state,parameters FROM operation_requests WHERE connection_id=%s AND state IN ('Prepared','Dispatching','Accepted','Running','Unknown') AND (target=%s OR parameters->>'jobName'=%s) ORDER BY created_at ASC",(self.connection_id,job_name,job_name))
                return [dict(row) for row in cur.fetchall()]


    def actor_allowed(self, username, kind="run"):
        with closing(self.connect()) as conn:
            with conn,conn.cursor() as cur:
                cur.execute("SELECT enabled AND (role='Admin' OR (role='Backup Operator' AND %s IN ('run','cancel'))) FROM app_users WHERE username=%s",(kind,username))
                row=cur.fetchone()
                return bool(row and row[0])


    def report(self, start, end):
        from backend.reports import period
        a,b=period(start,end)
        with closing(self.connect()) as conn:
            with conn,conn.cursor() as cur:
                query=" FROM session_observations WHERE connection_id=%s AND payload->>'type'='Backup' AND (payload->>'started')::timestamptz >= %s AND (payload->>'started')::timestamptz < %s"
                cur.execute("SELECT count(*)"+query,(self.connection_id,a,b))
                total=cur.fetchone()[0]
                cur.execute("SELECT payload,last_seen_at"+query+" ORDER BY (payload->>'started')::timestamptz DESC,job_id DESC LIMIT 5000",(self.connection_id,a,b))
                rows=cur.fetchall()
                cur.execute("SELECT min(first_seen_at),max(last_seen_at) FROM session_observations WHERE connection_id=%s",(self.connection_id,))
                first,last=cur.fetchone()
                cur.execute("SELECT name FROM connections WHERE id=%s",(self.connection_id,))
                source=cur.fetchone()
                return {"scope":{"connectionId":self.connection_id,"name":source[0] if source else "Configured environment"},"generatedAt":datetime.now(timezone.utc).isoformat(),"dateFrom":start.isoformat(),"dateTo":end.isoformat(),"timezone":"Asia/Makassar","sessions":[{**row,"observedAt":seen.isoformat()} for row,seen in rows],"total":total,"limit":5000,"truncated":total>5000,"firstObservation":first.isoformat() if first else None,"lastObservation":last.isoformat() if last else None,"coverage":"Application-observed sessions only; historical Catalog pruning and unobserved sessions are not included.","restoreVerified":False}


    def policies(self):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id,name,owner,revision,state,definition,created_at,updated_at FROM protection_policies WHERE connection_id=%s ORDER BY name LIMIT 100",(self.connection_id,))
                return [dict(row) for row in cur.fetchall()]

    def prepare_provisioning(self, key, actor, plan):
        from uuid import uuid4
        rows=plan["changes"]
        if not rows:raise ValueError("Provisioning rehearsal requires at least one VM.")
        summary=f"{len(rows)} VM{'s' if len(rows)!=1 else ''} · {plan['policy']['name']}"
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT enabled,role FROM app_users WHERE username=%s FOR SHARE",(actor,))
                user=cur.fetchone()
                if not user or not user["enabled"] or user["role"]!="Admin":raise PermissionError("Administrator permission was revoked.")
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":key:"+str(key),))
                existing=None
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s AND idempotency_key=%s",(self.connection_id,str(key)))
                existing=cur.fetchone()
                if existing:
                    if existing["actor"]!=actor:raise ValueError("Request key belongs to another operator.")
                    return dict(existing)
                for row in rows:
                    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":inventory:"+row["inventoryId"],))
                    cur.execute("SELECT * FROM protection_assignments WHERE connection_id=%s AND inventory_vm_id=%s FOR UPDATE",(self.connection_id,row["inventoryId"]))
                    assigned=cur.fetchone()
                    if assigned and assigned["state"] not in ("Failed","Retired"):
                        raise ValueError("At least one selected VM already has a staged onboarding assignment.")
                    cur.execute("SELECT id FROM operation_requests WHERE connection_id=%s AND kind='provision' AND state IN ('Prepared','Dispatching') AND parameters->'inventoryIds' ? %s",(self.connection_id,row["inventoryId"]))
                    if cur.fetchone():
                        raise ValueError("A provisioning rehearsal for at least one selected VM is already in progress.")
                cur.execute("INSERT INTO connections(id,name,provider) VALUES(%s,'Bareos Director','bareos') ON CONFLICT(id) DO NOTHING",(self.connection_id,))
                revision_id=str(uuid4())
                payload=Json({**plan,"simulationOnly":plan.get("mode")!="live"})
                cur.execute("INSERT INTO configuration_revisions(id,connection_id,policy_id,policy_revision,actor,state,payload) VALUES(%s,%s,%s,%s,%s,'Prepared',%s)",(revision_id,self.connection_id,plan.get("policyId"),plan.get("policyRevision") or 0,actor,payload))
                for row in rows:
                    assignment_id=str(uuid4())
                    params=(assignment_id,self.connection_id,row["inventoryId"],row["instanceUuid"],revision_id,plan.get("policyId"),plan.get("policyRevision") or 0,row["job"],row["fileset"],row["pool"],row["storage"],"Prepared")
                    cur.execute("INSERT INTO protection_assignments(id,connection_id,inventory_vm_id,instance_uuid,configuration_revision_id,policy_id,policy_revision,job_name,fileset_name,pool_name,storage_name,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,inventory_vm_id) DO UPDATE SET instance_uuid=excluded.instance_uuid,configuration_revision_id=excluded.configuration_revision_id,policy_id=excluded.policy_id,policy_revision=excluded.policy_revision,job_name=excluded.job_name,fileset_name=excluded.fileset_name,pool_name=excluded.pool_name,storage_name=excluded.storage_name,state=excluded.state,updated_at=now()",params)
                operation_id=str(uuid4())
                parameters={"summary":summary,"vmCount":len(rows),"inventoryIds":[row["inventoryId"] for row in rows],"policyName":plan["policy"]["name"],"simulationOnly":plan.get("mode")!="live","revisionId":revision_id}
                cur.execute("INSERT INTO operation_requests(id,connection_id,idempotency_key,kind,target,state,actor,parameters) VALUES(%s,%s,%s,'provision',%s,'Prepared',%s,%s) RETURNING *",(operation_id,self.connection_id,str(key),revision_id,actor,Json(parameters)))
                operation=dict(cur.fetchone())
                self.operation_audit(cur,operation)
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,'provision.revision.prepared',%s)",(self.connection_id,actor,Json({"revisionId":revision_id,"vmCount":len(rows),"policyName":plan["policy"]["name"],"simulationOnly":plan.get("mode")!="live"})))
                return operation

    def prepare_lifecycle(self, key, actor, plan):
        from uuid import uuid4
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT enabled,role FROM app_users WHERE username=%s FOR SHARE",(actor,))
                user=cur.fetchone()
                if not user or not user["enabled"] or user["role"]!="Admin":raise PermissionError("Administrator permission was revoked.")
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":key:"+str(key),))
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(self.connection_id+":lifecycle:"+plan["jobName"],))
                cur.execute("SELECT * FROM operation_requests WHERE connection_id=%s AND idempotency_key=%s",(self.connection_id,str(key)))
                existing=cur.fetchone()
                if existing:
                    payload=self.provision_revision(existing["target"]) if existing["kind"]=="provision" else None
                    if existing["actor"]!=actor or existing["kind"]!="provision" or not payload or payload["payload"].get("kind")!="lifecycle" or payload["payload"].get("action")!=plan["action"] or payload["payload"].get("jobName")!=plan["jobName"] or payload["payload"].get("proofRevision")!=plan["proofRevision"] or payload["payload"].get("reviewDigest")!=plan["reviewDigest"] or payload["payload"].get("definition")!=plan.get("definition"):
                        raise ValueError("Request key belongs to another lifecycle intent.")
                    return dict(existing)
                cur.execute("SELECT id FROM operation_requests WHERE connection_id=%s AND kind='provision' AND state IN ('Prepared','Dispatching','Accepted','Running','Unknown') AND parameters->>'jobName'=%s",(self.connection_id,plan["jobName"]))
                if cur.fetchone():raise ValueError("An unresolved lifecycle operation already exists for this job.")
                cur.execute("INSERT INTO connections(id,name,provider) VALUES(%s,'Bareos Director','bareos') ON CONFLICT(id) DO NOTHING",(self.connection_id,))
                revision_id=str(uuid4())
                cur.execute("INSERT INTO configuration_revisions(id,connection_id,policy_id,policy_revision,actor,state,payload) VALUES(%s,%s,NULL,%s,%s,'Prepared',%s)",(revision_id,self.connection_id,plan["proofRevision"],actor,Json(plan)))
                operation_id=str(uuid4())
                parameters={"summary":plan["summary"],"jobName":plan["jobName"],"lifecycleAction":plan["action"],"proofRevision":plan["proofRevision"],"revisionId":revision_id}
                cur.execute("INSERT INTO operation_requests(id,connection_id,idempotency_key,kind,target,state,actor,parameters) VALUES(%s,%s,%s,'provision',%s,'Prepared',%s,%s) RETURNING *",(operation_id,self.connection_id,str(key),revision_id,actor,Json(parameters)))
                operation=dict(cur.fetchone())
                self.operation_audit(cur,operation)
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,'lifecycle.revision.prepared',%s)",(self.connection_id,actor,Json({"revisionId":revision_id,"jobName":plan["jobName"],"action":plan["action"],"proofRevision":plan["proofRevision"]})))
                return operation

    def provision_revision(self, revision_id):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM configuration_revisions WHERE connection_id=%s AND id=%s",(self.connection_id,str(revision_id)))
                row=cur.fetchone()
                return dict(row) if row else None

    def finish_provisioning(self, revision_id, actor, state, details):
        if state not in ("Validated","Failed"):raise ValueError("Unsupported provisioning revision state.")
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM configuration_revisions WHERE connection_id=%s AND id=%s FOR UPDATE",(self.connection_id,str(revision_id)))
                row=cur.fetchone()
                if not row:return None
                cur.execute("UPDATE configuration_revisions SET state=%s,payload=payload || %s,updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",(state,Json(details),self.connection_id,str(revision_id)))
                revision=dict(cur.fetchone())
                assignment_state="Retired" if details.get("liveApplied") else "Prepared" if state=="Validated" else "Failed"
                cur.execute("UPDATE protection_assignments SET state=%s,updated_at=now() WHERE connection_id=%s AND configuration_revision_id=%s",(assignment_state,self.connection_id,str(revision_id)))
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,%s,%s)",(self.connection_id,actor,"provision.revision."+state.lower(),Json({"revisionId":str(revision_id),"simulationOnly":not bool(details.get("liveApplied")),"vmCount":len(revision["payload"].get("changes",[]))})))
                return revision

    def finish_lifecycle(self, revision_id, actor, state, details):
        if state not in ("Validated","Failed"):raise ValueError("Unsupported lifecycle revision state.")
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM configuration_revisions WHERE connection_id=%s AND id=%s FOR UPDATE",(self.connection_id,str(revision_id)))
                row=cur.fetchone()
                if not row:return None
                cur.execute("UPDATE configuration_revisions SET state=%s,payload=payload || %s,updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",(state,Json(details),self.connection_id,str(revision_id)))
                revision=dict(cur.fetchone())
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,%s,%s)",(self.connection_id,actor,"lifecycle.revision."+state.lower(),Json({"revisionId":str(revision_id),"jobName":revision["payload"].get("jobName"),"action":revision["payload"].get("action"),"state":state})))
                return revision

    def save_policy(self, body, actor):
        from uuid import uuid4
        import psycopg2.errors
        definition={k:body[k] for k in ('storage','freshness_hours','retention_days','maximum_volumes','schedule','time_wita')}
        try:
            with closing(self.connect()) as conn:
                with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT enabled,role FROM app_users WHERE username=%s FOR SHARE",(actor,))
                    user=cur.fetchone()
                    if not user or not user['enabled'] or user['role']!='Admin':raise PermissionError('Administrator permission was revoked.')
                    cur.execute("INSERT INTO connections(id,name,provider) VALUES(%s,'Bareos Director','bareos') ON CONFLICT(id) DO NOTHING",(self.connection_id,))
                    if body.get('id'):
                        cur.execute("UPDATE protection_policies SET name=%s,definition=%s,revision=revision+1,updated_at=now() WHERE connection_id=%s AND id=%s AND revision=%s AND state='Draft' RETURNING *",(body['name'],Json(definition),self.connection_id,str(body['id']),body['expected_revision']))
                        row=cur.fetchone()
                        if not row:raise ValueError('Policy revision changed or is no longer editable. Reload the current policy.')
                        event='policy.draft.updated'
                    else:
                        cur.execute("INSERT INTO protection_policies(id,connection_id,name,owner,definition) VALUES(%s,%s,%s,%s,%s) RETURNING *",(str(uuid4()),self.connection_id,body['name'],actor,Json(definition)))
                        row=cur.fetchone();event='policy.draft.created'
                    cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,%s,%s)",(self.connection_id,actor,event,Json({'policyId':str(row['id']),'name':row['name'],'revision':row['revision'],'state':'Draft'})))
                    return dict(row)
        except psycopg2.errors.UniqueViolation:raise ValueError('A policy with this name already exists.')


    def alerts(self):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM session_alerts WHERE connection_id=%s ORDER BY CASE WHEN state='Resolved' THEN 1 ELSE 0 END,last_seen_at DESC LIMIT 100",(self.connection_id,))
                return [dict(row) for row in cur.fetchall()]

    def acknowledge(self, alert_id, revision, actor):
        with closing(self.connect()) as conn:
            with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT enabled,role FROM app_users WHERE username=%s FOR SHARE",(actor,))
                user=cur.fetchone()
                if not user or not user['enabled'] or user['role']!='Admin':raise PermissionError()
                cur.execute("SELECT * FROM session_alerts WHERE connection_id=%s AND id=%s FOR UPDATE",(self.connection_id,str(alert_id)))
                row=cur.fetchone()
                if not row:raise ValueError('Alert is not available in this environment.')
                if row['state']=='Acknowledged' and row['acknowledged_by']==actor:return dict(row)
                if row['state']!='Open' or row['revision']!=revision:raise ValueError('Alert changed. Reload its current state.')
                cur.execute("UPDATE session_alerts SET state='Acknowledged',acknowledged_by=%s,revision=revision+1,last_seen_at=now() WHERE id=%s RETURNING *",(actor,str(alert_id)))
                result=dict(cur.fetchone())
                cur.execute("INSERT INTO audit_events(connection_id,actor,event_type,details) VALUES(%s,%s,'alert.acknowledged',%s)",(self.connection_id,actor,Json({'alertId':str(alert_id),'job':row['job_name'],'sourceJobId':row['source_job_id']})))
                return result
