import pytest
from backend.recovery import normalize_recovery


def source(**overrides):
    row={"jobid":"1","name":"VMware-safe","level":"F","jobstatus":"T","purgedfiles":"0","jobbytes":"100","media":[{"volumename":"safe-1"},{"volumename":"safe-1"}]}
    row.update(overrides)
    return {"sourceJobId":1,"jobIds":[1],"chain":[row],"engineResolved":True}


def test_catalog_media_is_not_restore_verification():
    result=normalize_recovery(source(),{"totalItems":1,"filenames":[{"filename":"/VMS/safe/disk.vmdk"}]},[{"name":"safe-1","status":"Append"}])
    assert result["blockers"]==[]
    assert result["mediaReadableVerified"] is False and result["restoreVerified"] is False
    assert len(result["chain"][0]["media"])==1
    assert result["items"][0]["kind"]=="Virtual disk backup"
    assert result["dispatchEnabled"] is False


def test_missing_full_pruned_metadata_and_purged_media_are_blockers():
    result=normalize_recovery(source(level="I",purgedfiles="1"),{"filenames":[]},[{"name":"safe-1","status":"Purged"}])
    assert len(result["blockers"])==3
    assert result["chain"][0]["metadataPruned"]


def test_missing_media_window_is_not_readable_evidence():
    result=normalize_recovery(source(),{"filenames":[]},[])
    assert result["blockers"]
    assert result["chain"][0]["media"][0]["status"]=="Not in retrieved Catalog window"


def test_gateway_only_uses_numeric_typed_read_commands(monkeypatch):
    import importlib.util, sys
    from types import SimpleNamespace as S
    from fastapi import FastAPI
    monkeypatch.setitem(sys.modules,"bareos_restapi",S(app=FastAPI(),get_current_user=lambda:None))
    spec=importlib.util.spec_from_file_location("extension_test","integration/backupcenter_extension.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    commands=[]
    def call(user,command):
        commands.append(command)
        if command.startswith("llist"):
            return {"jobs":[{"jobid":"1","name":"VMware-safe","type":"B","jobstatus":"T","clientid":"1","filesetid":"1","password":"secret"}]}
        if command.startswith(".bvfs"):
            return {"jobids":[{"id":"1"}]}
        return {"jobmedia":[{"volumename":"safe-1"}]}
    monkeypatch.setattr(module,"call",call)
    result=module.recovery(1,S())
    assert "secret" not in str(result)
    assert commands==["llist jobid=1",".bvfs_get_jobids jobid=1","llist jobid=1","list jobmedia jobid=1"]


def test_isolated_export_plan_is_fixed_and_scope_blocks_before_dispatch(monkeypatch,tmp_path):
    import importlib.util,sys
    from types import SimpleNamespace as S
    from fastapi import FastAPI,HTTPException
    from uuid import UUID
    import pytest
    monkeypatch.setitem(sys.modules,'bareos_restapi',S(app=FastAPI(),get_current_user=lambda:None))
    chain={'sourceJobId':1,'jobIds':[1],'chain':[{'jobid':'1','name':'VMware-safe','clientid':'1','level':'F','purgedfiles':'0','media':[{'volumename':'safe-1'}]}]}
    def call(user,command):
        if command.startswith('list files'):return {'filenames':[{'filename':'/VMS/safe/disk.vmdk'}]}
        if command=='show jobs':return {'jobs':{'VMware-safe':{'client':'bareos-fd','fileset':'safe','storage':['safe']},'RestoreFiles':{'type':'Restore'}}}
        if command=='show filesets':return {'filesets':{'safe':{'include':[{'plugin':['module_name=bareos-fd-vmware']}]}}}
        if command=='list clients':return {'clients':[{'clientid':'1','name':'bareos-fd'}]}
        raise AssertionError(command)
    monkeypatch.setitem(sys.modules,'backupcenter_extension',S(call=call,recovery=lambda job,user:chain))
    spec=importlib.util.spec_from_file_location('restore_test','integration/backupcenter_restore.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    user=S(jsonDirector=S(call=lambda command:(_ for _ in ()).throw(AssertionError('No dispatch authorized'))))
    uid=UUID('12345678-1234-1234-1234-123456789abc')
    plan=module.export_plan(1,uid,user)
    assert 'replace=never' in plan['command'] and 'localvmdk=yes' in plan['command']
    assert ' fileset=safe restorejob=RestoreFiles' in plan['command']
    assert plan['destination'].endswith(str(uid)) and 'select all done yes' in plan['command']
    monkeypatch.setattr(module,'APPROVAL',tmp_path/'absent-scope.json')
    with pytest.raises(HTTPException) as e:module.export_disks(module.ExportRequest(job_id=1,request_id=uid,confirmed=True),user)
    assert e.value.status_code==403


@pytest.mark.parametrize("mode",["success","http500","timeout"])
def test_restore_dispatch_is_durable_and_uses_the_original_key(monkeypatch,mode):
    import asyncio,httpx
    from uuid import uuid4
    from backend.tests.test_operations import FakeGateway
    monkeypatch.setattr("backend.operations.prepare_target",lambda *args:None)
    from backend.operations import dispatch
    async def run():
        g=FakeGateway();g.restore_enabled=True;g.restore_test_job='VMware-safe'
        async def get(client,path,query=None):
            if path.startswith('/backupcenter/recovery/'):
                return {'chain':[{'level':'F','purgedfiles':'0','media':[{'volumename':'safe-1'}]}]}
            return {'name':'VMware-safe','type':'B','jobstatus':'T'}
        g.get=get
        key=uuid4();op=g.store.prepare('restore','1',key)
        sent=[]
        def handle(request):
            assert g.store.rows[op['id']]['state']=='Dispatching'
            assert str(key).encode() in request.content
            sent.append(request)
            if mode=='timeout':raise httpx.ReadTimeout('fixture timeout',request=request)
            return httpx.Response(500 if mode=='http500' else 200,json={'jobid':42})
        original=httpx.AsyncClient
        monkeypatch.setattr('backend.operations.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle)))
        await dispatch(g,op);await dispatch(g,op)
        assert len(sent)==1 and g.store.rows[op['id']]['state']==('Accepted' if mode=='success' else 'Unknown')
    asyncio.run(run())
