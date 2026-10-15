import asyncio,json
from uuid import uuid4
import pytest
from integration.onboarding_contract import build
from backend.provisioning import preview
from backend.onboarding_target import apply_target
from backend.tests.test_operations import FakeGateway
from backend.operations import dispatch
UID='5208e076-eb89-9f06-2ef2-790ac92b4d71'
def test_review_bundle_is_deterministic_and_has_dedicated_repository():
    p=build(UID,'PNET');assert p==build(UID,'PNET')
    assert p['folder']=='/mnt/bareos-smb/PNET'
    assert 'uuid='+UID in p['files']['bareos-dir.d/fileset/PNET.conf']
    assert ':vmname=' not in p['files']['bareos-dir.d/fileset/PNET.conf']
    assert ':folder=' not in p['files']['bareos-dir.d/fileset/PNET.conf']
    assert ':dc=' not in p['files']['bareos-dir.d/fileset/PNET.conf']
    assert 'Priority = 16' in p['files']['bareos-dir.d/job/PNET.conf']
    assert 'AutoPrune = no' in p['files']['bareos-dir.d/pool/PNET.conf']
    assert 'PowerOn' not in ''.join(p['files'].values())
def test_review_contract_rejects_path_or_noncanonical_identity():
    for label in ('../PNET','PNET/x','PNET test'):
        with pytest.raises(ValueError):build(UID,label)
    with pytest.raises(ValueError):build(UID.replace('-',''),'PNET')
def test_approved_preview_is_live_and_keeps_first_backup_separate():
    row={'id':str(uuid4()),'instanceUuid':UID,'name':'PNET','association':'Unassigned','template':False}
    p=preview([row],{'name':'VeeamSMB','enabled':True,'mediaType':'SMBFile'},live_uuids={UID})
    assert p['mode']=='live' and p['changes'][0]['job']=='VMware-PNET'
    assert 'No first backup is started by Apply' in ' '.join(p['blockers'])
    with pytest.raises(ValueError):preview([row,row],{'name':'VeeamSMB','enabled':True,'mediaType':'SMBFile'},live_uuids={UID})
def test_transport_scope_denies_before_launch(monkeypatch):
    monkeypatch.setattr('backend.onboarding_target.dotenv_values',lambda _: {})
    monkeypatch.setattr('backend.onboarding_target.subprocess.run',lambda *a,**k:pytest.fail('SSH must not run'))
    with pytest.raises(ValueError,match='scope'):apply_target({'changes':[{'instanceUuid':UID}]},uuid4())
def test_live_worker_uses_typed_transport_and_records_real_apply(monkeypatch):
    async def scenario():
        g=FakeGateway();rid=str(uuid4());g.store.revisions[rid]={'id':rid,'state':'Prepared','payload':{'mode':'live','changes':[{'instanceUuid':UID}]}}
        op=g.store.prepare('provision',rid,uuid4())
        calls=[]
        def apply(plan,key):calls.append(key);return {'liveApplied':True,'simulationOnly':False,'message':'Configured; first backup separate'}
        monkeypatch.setattr('backend.onboarding_target.apply_target',apply)
        await dispatch(g,op)
        assert len(calls)==1 and g.store.rows[op['id']]['state']=='Completed'
        assert g.store.revisions[rid]['payload']['liveApplied'] is True
    asyncio.run(scenario())
def test_uncertain_live_apply_never_becomes_retryable_failed_assignment(monkeypatch):
    async def scenario():
        g=FakeGateway();rid=str(uuid4());g.store.revisions[rid]={'id':rid,'state':'Prepared','payload':{'mode':'live'}}
        op=g.store.prepare('provision',rid,uuid4())
        def failure(*a):raise RuntimeError('transport interrupted')
        monkeypatch.setattr('backend.onboarding_target.apply_target',failure)
        await dispatch(g,op)
        assert g.store.rows[op['id']]['state']=='Unknown'
        assert g.store.revisions[rid]['state']=='Prepared'
    asyncio.run(scenario())
