from uuid import uuid4
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from backend import app as module,auth
from backend.provisioning import preview
from backend.tests.test_provisioning import VM,STORAGE
from backend.tests.test_operations import HEADERS

BODY={'name':'Daily VM draft','storage':'VeeamSMB','freshness_hours':24,'retention_days':30,'maximum_volumes':6,'schedule':'Daily','time_wita':'21:30'}


def test_policy_requires_explicit_valid_targets_and_revisions():
    assert module.PolicyRequest(**BODY).freshness_hours==24
    with pytest.raises(ValidationError):module.PolicyRequest(**{**BODY,'freshness_hours':1})
    with pytest.raises(ValidationError):module.PolicyRequest(**{**BODY,'id':uuid4(),'expected_revision':0})
    with pytest.raises(ValidationError):module.PolicyRequest(**{**BODY,'time_wita':'25:00'})
    with pytest.raises(ValidationError):module.PolicyRequest(**{**BODY,'retention_days':0})


def test_viewer_cannot_save_or_override_policy_owner(monkeypatch):
    monkeypatch.setattr(auth,'session_user',lambda token:{'username':'viewer','role':'Viewer'})
    with TestClient(module.app) as client:
        assert client.post('/api/policies',headers=HEADERS,json=BODY).status_code==403
    with pytest.raises(ValidationError):module.PolicyRequest(**{**BODY,'owner':'admin'})


def test_policy_preview_keeps_schedule_disabled_and_records_revision():
    policy={'id':uuid4(),'name':'Monthly draft','revision':2,'definition':{'retention_days':60,'maximum_volumes':12}}
    result=preview([VM],STORAGE,policy)
    assert 'Volume Retention = 60 days' in result['changes'][0]['configuration']
    assert 'Maximum Volumes = 12' in result['changes'][0]['configuration']
    assert 'Schedule =' not in result['changes'][0]['configuration']
    assert result['policyRevision']==2 and result['applyEnabled'] is True
