import asyncio
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from backend import app as module
from backend.operations import dispatch,reconcile


class FakeStore:
    configured=True
    def __init__(self):self.rows={};self.transitions=[];self.revisions={}
    def operation_key(self,key):return next((r for r in self.rows.values() if str(r["idempotency_key"])==str(key)),None)
    def operations(self,pending=False):return list(self.rows.values())
    def prepare(self,kind,target,key,actor="testadmin"):
        existing=self.operation_key(key)
        if existing:
            if existing["kind"]!=kind or existing["target"]!=target:raise ValueError("Key conflict")
            return existing
        if any(r["kind"]==kind and r["target"]==target and r["state"] not in ("Completed","Failed") for r in self.rows.values()):raise ValueError("Unresolved operation")
        row={"id":str(uuid4()),"idempotency_key":str(key),"kind":kind,"target":target,"state":"Prepared","job_id":int(target) if kind=="cancel" else None,"parameters":{},"actor":actor}
        self.rows[row["id"]]=row
        return dict(row)
    def provision_revision(self, revision_id):return self.revisions.get(str(revision_id))
    def finish_provisioning(self, revision_id, actor, state, details):
        self.revisions[str(revision_id)]["state"]=state
        self.revisions[str(revision_id)]["payload"]={**self.revisions[str(revision_id)]["payload"],**details}
        return dict(self.revisions[str(revision_id)])
    def actor_allowed(self, username, kind="run"):return True
    def transition(self,oid,expected,state,job_id=None,message="",session_status=None):
        row=self.rows[oid]
        if row["state"] not in expected:return None
        row.update(state=state,parameters={**row["parameters"],"message":message})
        if job_id:row["job_id"]=job_id
        self.transitions.append(state)
        return dict(row)


class FakeGateway:
    def __init__(self):
        self.store=FakeStore();self.base="https://bareos.test";self.token="test";self.context=True;self.lock=asyncio.Lock();self.cached_at=0
        self.status="R";self.active_same_job=False
    async def get(self,client,path,query=None):
        if path=="/configuration/jobs":return {"jobs":{"VMware-safe":{"name":"VMware-safe","type":"Backup","enabled":True}}}
        if path.startswith("/control/jobs?"):
            return {"totalItems":1 if self.active_same_job else 0,"jobs":[{"name":"VMware-safe","jobstatus":"R"}] if self.active_same_job else []}
        return {"jobid":"12","name":"VMware-safe","type":"B","jobstatus":self.status}


HEADERS={"Origin":"http://127.0.0.1:3000","X-Backup-Center-Action":"confirmed"}

def test_operation_route_rejects_csrf_and_extra_fields(monkeypatch):
    with TestClient(module.app) as client:
        assert client.post("/api/operations",json={}).status_code==403
        assert client.post("/api/operations",headers=HEADERS,json={"kind":"run","target":"VMware-safe","idempotency_key":str(uuid4()),"confirmed":True,"pluginoptions":"injected"}).status_code==422


def test_route_replays_key_and_blocks_unresolved_target(monkeypatch):
    # Construct lock in route's async loop, not the test thread.
    holder={}
    def fake_gateway():
        if "g" not in holder:holder["g"]=FakeGateway()
        return holder["g"]
    monkeypatch.setattr(module,"gateway",fake_gateway)
    body={"kind":"run","target":"VMware-safe","idempotency_key":str(uuid4()),"confirmed":True}
    with TestClient(module.app) as client:
        first=client.post("/api/operations",headers=HEADERS,json=body)
        assert first.status_code==202
        second=client.post("/api/operations",headers=HEADERS,json=body)
        assert second.json()["id"]==first.json()["id"]
        other=dict(body,idempotency_key=str(uuid4()))
        assert client.post("/api/operations",headers=HEADERS,json=other).status_code==409
        assert len(holder["g"].store.rows)==1


def test_unsafe_job_and_finished_session_fail_preflight(monkeypatch):
    holder={}
    def gateway():
        if "g" not in holder:holder["g"]=FakeGateway();holder["g"].status="T"
        return holder["g"]
    monkeypatch.setattr(module,"gateway",gateway)
    with TestClient(module.app) as client:
        for kind,target in [("run","VMware-safe cancel=yes"),("cancel","12")]:
            result=client.post("/api/operations",headers=HEADERS,json={"kind":kind,"target":target,"idempotency_key":str(uuid4()),"confirmed":True})
            assert result.status_code==409
        assert not holder["g"].store.rows


@pytest.mark.parametrize("mode",["success","timeout","http500"])
def test_dispatch_commits_before_send_and_never_resends(monkeypatch,mode):
    async def scenario():
        gateway=FakeGateway();op=gateway.store.prepare("run","VMware-safe",uuid4());sent=[]
        def handler(request):
            assert gateway.store.rows[op["id"]]["state"]=="Dispatching"
            sent.append(request)
            if mode=="timeout":raise httpx.ReadTimeout("unknown",request=request)
            return httpx.Response(500 if mode=="http500" else 200,json={"jobid":12})
        original=httpx.AsyncClient
        monkeypatch.setattr("backend.operations.httpx.AsyncClient",lambda **kwargs:original(transport=httpx.MockTransport(handler)))
        await dispatch(gateway,op)
        await dispatch(gateway,op)
        assert len(sent)==1
        assert gateway.store.rows[op["id"]]["state"]==("Accepted" if mode=="success" else "Unknown")
    asyncio.run(scenario())


def test_cancel_acknowledgement_is_not_terminal(monkeypatch):
    async def scenario():
        g=FakeGateway();op=g.store.prepare("cancel","12",uuid4())
        original=httpx.AsyncClient
        monkeypatch.setattr("backend.operations.httpx.AsyncClient",lambda **kwargs:original(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={}))))
        await dispatch(g,op)
        accepted=g.store.rows[op["id"]]
        assert accepted["state"]=="Accepted"
        await reconcile(g,accepted)
        assert accepted["state"]=="Accepted"
        g.status="A"
        await reconcile(g,accepted)
        assert accepted["state"]=="Completed"
    asyncio.run(scenario())


def test_cancellation_race_reports_finished_job_not_canceled():
    async def scenario():
        g=FakeGateway();op=g.store.prepare("cancel","12",uuid4());g.store.transition(op["id"],["Prepared"],"Accepted",12);g.status="T"
        await reconcile(g,g.store.rows[op["id"]])
        assert g.store.rows[op["id"]]["state"]=="Failed"
    asyncio.run(scenario())


def test_journal_failure_never_queues_a_command(monkeypatch):
    holder={}
    def gateway():
        if "g" not in holder:holder["g"]=FakeGateway()
        def fail(*args):raise RuntimeError("database offline")
        holder["g"].store.prepare=fail
        return holder["g"]
    monkeypatch.setattr(module,"gateway",gateway)
    with TestClient(module.app) as client:
        result=client.post("/api/operations",headers=HEADERS,json={"kind":"run","target":"VMware-safe","idempotency_key":str(uuid4()),"confirmed":True})
        assert result.status_code==503
        assert not holder["g"].store.rows


def test_active_backup_job_cannot_be_queued_again(monkeypatch):
    holder={}
    def gateway():
        if "g" not in holder:holder["g"]=FakeGateway();holder["g"].active_same_job=True
        return holder["g"]
    monkeypatch.setattr(module,"gateway",gateway)
    with TestClient(module.app) as client:
        response=client.post("/api/operations",headers=HEADERS,json={"kind":"run","target":"VMware-safe","idempotency_key":str(uuid4()),"confirmed":True})
        assert response.status_code==409
        assert not holder["g"].store.rows


def test_deferred_operations_fail_before_remote_preflight(monkeypatch):
    async def run():
        g=FakeGateway();g.operation_dispatch_enabled=False
        async def forbidden(*args,**kwargs):pytest.fail('Deferred operations must not reach the remote preflight')
        g.get=forbidden
        op=g.store.prepare('run','VMware-safe',uuid4())
        await dispatch(g,op)
        assert g.store.rows[op['id']]['state']=='Failed'
        assert 'Dispatching' not in g.store.transitions
    asyncio.run(run())


def test_provisioning_rehearsal_completes_without_remote_io():
    async def run():
        g=FakeGateway()
        revision_id=str(uuid4())
        g.store.revisions[revision_id]={"id":revision_id,"state":"Prepared","payload":{"changes":[{"inventoryId":"scoped-id","job":"BC-safe","configuration":'Job {\n  Name = "BC-safe"\n}\n'}],"policy":{"name":"Draft policy"}}}
        op=g.store.prepare("provision",revision_id,uuid4())
        await dispatch(g,op)
        assert g.store.rows[op["id"]]["state"]=="Completed"
        assert g.store.revisions[revision_id]["state"]=="Validated"
        assert "no Bareos configuration was loaded" in g.store.rows[op["id"]]["parameters"]["message"]
    asyncio.run(run())
