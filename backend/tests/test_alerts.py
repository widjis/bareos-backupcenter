from backend.alerts import signals
from fastapi.testclient import TestClient
from backend import app as module,auth
from backend.tests.test_operations import HEADERS
from uuid import uuid4


def snapshot(sessions,errors=None):
    return {'connection':'connected','sourceErrors':errors or {},'jobs':[{'name':'VMware-safe','type':'Backup'}],'sessions':sessions}


def session(job_id,status,kind='Backup'):
    return {'id':job_id,'name':'VMware-safe','status':status,'type':kind}


def test_running_backup_does_not_resolve_previous_failure():
    data=snapshot([session(1,'Failed'),session(2,'Running')])
    assert signals(data)['VMware-safe']['id']==1


def test_later_terminal_success_is_resolution_evidence():
    assert signals(snapshot([session(1,'Warning'),session(2,'Succeeded')]))['VMware-safe']['status']=='Succeeded'
    assert signals(snapshot([session(1,'Failed'),session(2,'Succeeded','Restore')]))['VMware-safe']['status']=='Failed'


def test_missing_source_never_resolves_or_reports_empty_success():
    assert signals(snapshot([session(2,'Succeeded')],{'sessions':'unavailable'})) is None
    assert signals({**snapshot([]),'connection':'stale'}) is None


def test_viewer_cannot_acknowledge(monkeypatch):
    monkeypatch.setattr(auth,'session_user',lambda token:{'username':'viewer','role':'Viewer'})
    with TestClient(module.app) as client:
        assert client.post('/api/alerts/'+str(uuid4())+'/ack',headers=HEADERS,json={'revision':1}).status_code==403
