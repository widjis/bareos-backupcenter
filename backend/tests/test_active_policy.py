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
