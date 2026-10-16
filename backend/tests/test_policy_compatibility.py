import pytest
from fastapi.testclient import TestClient
from backend.policy_compatibility import current_capabilities,helper_compatible,local_preview

def test_readable_legacy_helper_does_not_enable_live_apply():
    r=current_capabilities({'jobs':[{'job':'VMware-PNET'}]},True)
    assert r['applyEnabled'] is False and r['helperCompatible'] is False
    assert 'older' in r['liveApplyBlocker']

@pytest.mark.parametrize('rows',[[],None,[{'triggerMode':'calendar'}]])
def test_missing_capability_evidence_is_not_positive(rows):
    assert not helper_compatible({'jobs':rows})

def test_verified_helper_still_requires_configured_feature():
    row=dict(triggerMode='calendar',afterJob=None,windowEndWita=None,retryCount=0,retryIntervalMinutes=30)
    assert current_capabilities({'jobs':[row],'executionReady':True},True)['applyEnabled']
    assert not current_capabilities({'jobs':[row]},False)['applyEnabled']
    assert not helper_compatible({'jobs':[row,{}]})

def test_local_preview_is_explicitly_unverified():
    r=local_preview({'definition':{'jobs':['VMware-PNET']},'reviewDigest':'a'*64})
    assert not r['applyEnabled'] and not r['targetVerified'] and r['verification']=='Local preview only'


def test_apply_never_dispatches_to_legacy_helper(monkeypatch):
    from backend import app as module
    monkeypatch.setattr('backend.auth.session_user',lambda _:dict(username='admin',role='Admin'))
    class Store:
        def actor_allowed(self,*args):return True
    import asyncio
    class Gateway:
        values={'BACKUPCENTER_POLICY_APPLY_ENABLED':'1'}
        store=Store()
        lock=asyncio.Lock()
    monkeypatch.setattr(module,'gateway',lambda:Gateway())
    calls=[]
    def invoke(body):
        calls.append(body['action'])
        assert body['action']=='current','Must never dispatch a mutation'
        return {'jobs':[{'job':'VMware-PNET'}]}
    monkeypatch.setattr('backend.policy_target.invoke',invoke)
    with TestClient(module.app) as client:
        r=client.post('/api/policies/active/apply',headers={'Origin':'http://127.0.0.1:3000','X-Backup-Center-Action':'confirmed'},json={'definition':{'jobs':['VMware-PNET'],'time_wita':'21:30','retention_days':30,'maximum_volumes':6},'request_id':'87b3599b-f544-4fc0-adfb-de4969b22c56','review_digest':'a'*64,'confirmed':True})
    assert r.status_code==409 and calls==['current']


def test_preview_old_helper_is_available_but_never_dispatchable(monkeypatch):
    from backend import app as module
    monkeypatch.setattr('backend.auth.session_user',lambda _:dict(username='admin',role='Admin'))
    def invoke(body):raise ValueError('trigger_mode: Extra inputs are not permitted')
    monkeypatch.setattr('backend.policy_target.invoke',invoke)
    with TestClient(module.app) as client:
        response=client.post('/api/policies/active/preview',headers={'Origin':'http://127.0.0.1:3000','X-Backup-Center-Action':'confirmed'},json={'definition':{'jobs':['VMware-PNET'],'time_wita':'21:30','retention_days':30,'maximum_volumes':6}})
    assert response.status_code==200
    r=response.json();assert r['applyEnabled'] is False and r['targetVerified'] is False
    assert r['verification']=='Local preview only' and 'older' in r['liveApplyBlocker']


def test_schema_compatibility_without_native_acceptance_never_enables_apply():
    row=dict(triggerMode='after_job',afterJob={},windowEndWita=None,retryCount=0,retryIntervalMinutes=30)
    r=current_capabilities({'jobs':[row]},True)
    assert r['helperCompatible'] is True
    assert r['applyEnabled'] is False
    assert 'native acceptance' in r['liveApplyBlocker']
