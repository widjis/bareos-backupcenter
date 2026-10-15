import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from backend.vm_restore import VMRestoreDestination,build_vm_restore_plan

def destination(**kw):
    return VMRestoreDestination(**({"vm_name":"PNET-RESTORE-TEST","datacenter":"DC1","folder":"/RestoreTests","host":"esx01.example.local","datastore":"DS1"}|kw))
def evidence(**kw):
    return {"sourceJobId":24,"jobIds":[23,24],"engineResolved":True,"blockers":[],"chain":[{"media":[{"name":"PNET-0009"}]}]}|kw

def test_review_never_dispatches_and_detects_uuid_without_leaking_plugin_secrets():
    p=build_vm_restore_plan(evidence(),destination(),"python:module_name=bareos-fd-vmware:uuid=abc:vcpass=hidden")
    assert p["uuidSource"] and not p["dispatchEnabled"] and not p["targetVerified"]
    assert p["jobIds"]==[23,24] and p["requiredMedia"]==["PNET-0009"]
    assert "hidden" not in str(p) and "command" not in p
    assert any("UUID" in b for b in p["blockers"])
    assert p["reviewDigest"]==build_vm_restore_plan(evidence(),destination(),"python:module_name=bareos-fd-vmware:uuid=abc")["reviewDigest"]
    assert p["reviewDigest"]!=build_vm_restore_plan(evidence(),destination(vm_name="OTHER"),"bareos-fd-vmware")["reviewDigest"]

@pytest.mark.parametrize("kw",[{"power":"on"},{"network":"connected"},{"overwrite":"Always"},{"folder":"/../prod"},{"vm_name":"x:yes"},{"host":"esx\nrun"},{"folder":"/a//b"},{"datastore":""}])
def test_unsafe_destinations_are_rejected(kw):
    with pytest.raises(ValidationError):destination(**kw)

def test_incomplete_chain_is_visible_and_path_source_still_requires_target_verification():
    p=build_vm_restore_plan(evidence(engineResolved=False,blockers=["Missing media"]),destination(),"python:module_name=bareos-fd-vmware:dc=DC1:vmname=PNET")
    assert not p["uuidSource"] and not p["dispatchEnabled"]
    assert "Missing media" in p["blockers"] and any("complete backup chain" in b for b in p["blockers"])

def test_review_endpoint_is_admin_only_and_does_not_dispatch(monkeypatch):
    import backend.app as a
    from types import SimpleNamespace
    import asyncio
    async def inspection(job_id):return evidence()
    calls=[]
    async def get(client,path):
        calls.append(path)
        if path.startswith('/control/jobs/'):return {"name":"VMware-PNET"}
        if path=='/configuration/jobs':return {"jobs":{"VMware-PNET":{"fileset":"VMware-PNET"}}}
        return {"filesets":{"VMware-PNET":{"include":[{"plugin":["python:module_name=bareos-fd-vmware:uuid=abc"]}]}}}
    g=SimpleNamespace(lock=asyncio.Lock(),context=True,get=get)
    monkeypatch.setattr(a,'gateway',lambda:g);monkeypatch.setattr(a,'recovery_inspection',inspection)
    headers={"Origin":"http://127.0.0.1:3000","X-Backup-Center-Action":"confirmed"}
    # Disable startup worker/store requirements by using the application without lifespan.
    client=TestClient(a.app)
    body={"source_job_id":24,"destination":destination().model_dump()}
    response=client.post('/api/recovery/vmware/plan',headers=headers,json=body)
    assert response.status_code==200,response.text
    assert not response.json()['dispatchEnabled'] and len(calls)==3
    monkeypatch.setattr('backend.auth.session_user',lambda _: {"username":"reader","role":"Viewer"})
    assert client.post('/api/recovery/vmware/plan',headers=headers,json=body).status_code==403


@pytest.mark.parametrize("mode",["success","timeout","changed"])
def test_direct_dispatch_claims_before_send_and_never_resends(monkeypatch,mode):
    import asyncio
    from uuid import uuid4
    from backend.tests.test_operations import FakeGateway
    from backend.operations import dispatch
    async def scenario():
        g=FakeGateway();g.operation_dispatch_enabled=True;g.values={"BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED":"1"}
        op=g.store.prepare("restore","24",uuid4());op['parameters']={"mode":"vmware-new-vm","destination":destination().model_dump(),"reviewDigest":"a"*64}
        g.store.rows[op['id']]['parameters']=op['parameters'];sent=[]
        def invoke(body):
            if body['action']=='plan':return {"dispatchEnabled":True,"reviewDigest":("b" if mode=="changed" else "a")*64}
            assert g.store.rows[op['id']]['state']=='Dispatching';sent.append(body)
            if mode=="timeout":raise TimeoutError()
            return {"jobid":42}
        monkeypatch.setattr('backend.direct_restore_target.invoke',invoke)
        await dispatch(g,op);await dispatch(g,op)
        assert len(sent)==(0 if mode=="changed" else 1)
        assert g.store.rows[op['id']]['state']=={"success":"Accepted","timeout":"Unknown","changed":"Failed"}[mode]
    asyncio.run(scenario())

def test_plugin_patch_is_opt_in_and_removes_network_before_create():
    from integration.patch_vmware_direct_restore import patch
    original='class Plugin:\n    allowed_options = [\n            "restore_powerstate",\n    ]\n    def start_restore_job(self):\n        check_option_bRC = self.check_plugin_options()\n        return self.vadp.prepare_vm_restore()\n    def create_vm(self):\n        found_dc = self.si.content.searchIndex.FindByInventoryPath(self.options["dc"])\n'
    result=patch(original)
    import ast
    ast.parse(result)
    assert patch(result)==result
    assert 'self.options.pop("uuid", None)' in result
    assert 'VirtualEthernetCard' in result and 'O_NOFOLLOW' in result
    assert 'Restore target already exists' in result


def test_direct_submit_binds_idempotency_to_actor_destination_and_digest(monkeypatch):
    import backend.app as a
    from backend.tests.test_operations import FakeGateway,FakeStore
    from uuid import uuid4
    class Store(FakeStore):
        def prepare(self,kind,target,key,actor,parameters):
            r=super().prepare(kind,target,key,actor);self.rows[r['id']]['parameters']=parameters;return self.rows[r['id']]
    g=FakeGateway();g.store=Store();g.values={"BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED":"1"};g.operation_dispatch_enabled=True
    monkeypatch.setattr(a,'gateway',lambda:g)
    async def plan(body,request):return {"dispatchEnabled":True,"reviewDigest":"a"*64}
    monkeypatch.setattr(a,'vm_restore_plan',plan)
    h={"Origin":"http://127.0.0.1:3000","X-Backup-Center-Action":"confirmed"}
    body={"source_job_id":24,"destination":destination().model_dump(),"idempotency_key":str(uuid4()),"review_digest":"a"*64,"confirmed":True}
    c=TestClient(a.app);r=c.post('/api/recovery/vmware/restore',headers=h,json=body)
    assert r.status_code==202,r.text
    assert c.post('/api/recovery/vmware/restore',headers=h,json=body).json()['id']==r.json()['id']
    body['destination']['vm_name']='PNET-RESTORE-OTHER'
    assert c.post('/api/recovery/vmware/restore',headers=h,json=body).status_code==409
    monkeypatch.setattr('backend.auth.session_user',lambda _:{"username":"operator","role":"Backup Operator"})
    assert c.post('/api/recovery/vmware/restore',headers=h,json=body).status_code==403


def test_result_preserves_execution_and_boot_evidence_and_requires_admin(monkeypatch):
    import backend.app as a
    from types import SimpleNamespace
    from uuid import uuid4
    row={"kind":"restore","parameters":{"mode":"vmware-new-vm"},"idempotency_key":str(uuid4())}
    monkeypatch.setattr(a,'gateway',lambda:SimpleNamespace(store=SimpleNamespace(operation=lambda _:row)))
    monkeypatch.setattr('backend.direct_restore_target.invoke',lambda _: {"state":"Completed","isolationVerified":True,"bootVerification":{"bootVerified":True,"finalPower":"poweredOff"}})
    c=TestClient(a.app);url='/api/recovery/vmware/result/'+str(uuid4());r=c.get(url)
    assert r.status_code==200 and r.json()['bootVerification']['bootVerified']
    monkeypatch.setattr('backend.auth.session_user',lambda _:{"username":"reader","role":"Viewer"})
    assert c.get(url).status_code==403
