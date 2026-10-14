import pytest
from backend.provisioning import preview, rehearse

VM={"id":"scoped-id","instanceUuid":"12345678-1234-1234-1234-123456789abc","name":"safe","template":False,"association":"Unassigned"}
STORAGE={"name":"VeeamSMB","mediaType":"SMBFile","enabled":True}


def test_preview_contains_no_secret_or_enabled_schedule():
    result=preview([VM],STORAGE)
    text=result['changes'][0]['configuration']
    assert 'uuid=12345678-1234-1234-1234-123456789abc' in text
    assert 'config_file=/etc/bareos/vmware-plugin.ini' in text
    assert 'Enabled = no' in text and 'Schedule =' not in text
    assert 'vcpass=' not in text and 'Storage {' not in text
    assert result['applyEnabled'] is True


@pytest.mark.parametrize('field,value',[('association','Candidate match'),('association','Ambiguous match'),('instanceUuid',None),('template',True)])
def test_ineligible_vm_cannot_generate_new_resources(field,value):
    with pytest.raises(ValueError):preview([{**VM,field:value}],STORAGE)


def test_same_name_different_uuid_has_distinct_resource_names():
    other={**VM,'instanceUuid':'12345678-1234-1234-1234-123456789abd'}
    result=preview([VM,other],STORAGE)
    assert result['changes'][0]['job']!=result['changes'][1]['job']


def test_preview_rejects_invalid_duplicate_and_oversized_selections():
    for selected in ([],[VM,VM],[{**VM,'instanceUuid':'-'*36}],[VM]*26):
        with pytest.raises(ValueError):preview(selected,STORAGE)


def test_rehearsal_uses_temporary_local_fixtures_only():
    result=rehearse(preview([VM],STORAGE))
    assert result["vmCount"]==1 and result["fileCount"]==1
    assert len(result["sha256"])==64
    assert result["manifest"]["simulationOnly"] is True
    assert "no Bareos configuration was loaded" in result["message"]


def test_preview_reports_required_script_mapping_extensions():
    result=preview([VM],STORAGE,baseline_jobs=["MTIMRWCNTDEV"])
    assert result["scriptReview"]["required"] is True
    assert result["scriptReview"]["baselineCount"] == 1
    assert result["scriptReview"]["additions"][0]["prepareAllowlist"]["script"] == "prepare-vm-backup"
    assert result["scriptReview"]["additions"][0]["retentionAllowlist"]["script"] == "chain-retention"
