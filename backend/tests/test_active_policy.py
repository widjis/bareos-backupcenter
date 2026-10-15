import pytest
from pydantic import ValidationError
from backend.active_policy import ActivePolicy,schedule

def definition(**kw):return {'jobs':['VMware-PNET'],'time_wita':'21:30','retention_days':30,'maximum_volumes':6,'automatic':True}|kw

def test_current_policy_and_manual_schedule_preserve_cadence():
    p=ActivePolicy(**definition());text=schedule('test',p.time_wita,p.automatic)
    assert 'Level=Full on 1 at 13:30' in text and 'Level=Full on 15 at 13:30' in text
    assert 'Level=Incremental on 16-31 at 13:30' in text
    assert 'Enabled = no' in schedule('test','23:59',False)
    assert 'at 15:59' in schedule('test','23:59',False)

@pytest.mark.parametrize('kw',[{'retention_days':29},{'retention_days':60,'maximum_volumes':6},{'time_wita':'20:30'},{'time_wita':'21:00'},{'jobs':[]},{'jobs':['VMware-PNET','VMware-PNET']}])
def test_invalid_policy_is_rejected(kw):
    with pytest.raises(ValidationError):ActivePolicy(**definition(**kw))

def test_policy_api_cannot_apply_for_non_admin(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import app
    monkeypatch.setattr('backend.auth.session_user',lambda _:{'username':'viewer','role':'Viewer'})
    client=TestClient(app)
    for path in ['/api/policies/active','/api/policies/active/status/12345678-1234-1234-1234-123456789abc']:
        assert client.get(path).status_code==403
    assert client.post('/api/policies/active/apply',headers={'Origin':'http://127.0.0.1:3000','X-Backup-Center-Action':'confirmed'},json={}).status_code==403


def test_active_policy_current_falls_back_locally_when_windows_transport_is_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as module
    monkeypatch.setattr('backend.auth.session_user',lambda _:{'username':'admin','role':'Admin'})

    class FakeGateway:
        values={}
        operation_jobs=frozenset({'VMware-PNET'})
        async def snapshot(self, refresh=False):
            return {
                'jobs':[{'name':'VMware-PNET','schedule':'VMwareTwiceMonthly','pool':'PNET'}],
                'pools':[{'name':'PNET','retentionDays':45,'maxVolumes':8}],
                'schedules':[{'name':'VMwareTwiceMonthly','rules':['Level=Full on 1 at 14:15']}],
            }

    monkeypatch.setattr(module,'gateway',lambda:FakeGateway())
    monkeypatch.setattr('backend.policy_target.invoke',lambda body: (_ for _ in ()).throw(ValueError('Managed policy transport is configured for this Windows environment.')))
    with TestClient(module.app) as client:
        response=client.get('/api/policies/active')
        assert response.status_code==200
        assert response.json()['jobs']==[{'job':'VMware-PNET','timeWita':'22:15','automatic':True,'retentionDays':45,'maximumVolumes':8}]


def test_active_policy_preview_falls_back_locally_when_windows_transport_is_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as module
    monkeypatch.setattr('backend.auth.session_user',lambda _:{'username':'admin','role':'Admin'})
    monkeypatch.setattr('backend.policy_target.invoke',lambda body: (_ for _ in ()).throw(ValueError('Managed policy transport is configured for this Windows environment.')))
    with TestClient(module.app) as client:
        response=client.post('/api/policies/active/preview',headers={'Origin':'http://127.0.0.1:3000','X-Backup-Center-Action':'confirmed'},json={'definition':definition()})
        assert response.status_code==200
        body=response.json()
        assert body['definition']['jobs']==['VMware-PNET']
        assert len(body['reviewDigest'])==64
