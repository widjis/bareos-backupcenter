import pytest
from fastapi.testclient import TestClient
from backend import app as module

HEADERS={"Origin":"http://127.0.0.1:3000","X-Backup-Center-Action":"confirmed"}

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr('backend.auth.session_user',lambda _:dict(username='admin',role='Admin'))
    class Store:
        def assignment_detail(self, job_name):
            return {"inventory_vm_id":"managed.pnet","instance_uuid":"11111111-1111-1111-1111-111111111111","storage_name":"repo-primary"}
        def lifecycle_operations(self, job_name):
            return []
        def latest_lifecycle_revision(self, job_name):
            return None
        def operation_key(self, request_id):
            return None
    class Gateway:
        operation_jobs={'VMware-PNET'}
        values={}
        store=Store()
        async def snapshot(self,force=False):
            assert force is True
            return {'jobs':[{'name':'VMware-PNET'}]}
    monkeypatch.setattr(module,'gateway',lambda:Gateway())
    with TestClient(module.app) as c: yield c

def test_preview_is_read_only_and_incomplete_proof_is_explicit(client):
    r=client.post('/api/jobs/disable/preview',headers=HEADERS,json={'job_name':'VMware-PNET'})
    assert r.status_code==200
    assert r.json()['executionSupported'] is False
    assert r.json()['blockers']
    assert r.json()['readiness']=="blocked"

def test_client_cannot_supply_authoritative_proof(client):
    r=client.post('/api/jobs/disable/preview',headers=HEADERS,json={'job_name':'VMware-PNET','trusted_role':'Admin','registry_evidence':{}})
    assert r.status_code==422

def test_scope_and_origin_are_enforced(client):
    assert client.post('/api/jobs/disable/preview',headers=HEADERS,json={'job_name':'Other'}).status_code==409
    assert client.post('/api/jobs/disable/preview',json={'job_name':'VMware-PNET'}).status_code==403

def test_viewer_cannot_request_preview(client,monkeypatch):
    monkeypatch.setattr('backend.auth.session_user',lambda _:dict(username='viewer',role='Viewer'))
    assert client.post('/api/jobs/disable/preview',headers=HEADERS,json={'job_name':'VMware-PNET'}).status_code==403

def test_no_disable_execution_route_exists(client):
    assert client.post('/api/jobs/disable',headers=HEADERS,json={'job_name':'VMware-PNET'}).status_code==405
    assert client.post('/api/jobs/lifecycle/disable/review',headers=HEADERS,json={'jobName':'VMware-PNET'}).status_code==200
