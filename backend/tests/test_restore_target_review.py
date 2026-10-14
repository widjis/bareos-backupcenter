import pytest
from integration.prepare_restore_target import prepare,rpc_objects


def test_helper_denies_non_root_before_any_side_effect(monkeypatch):
    monkeypatch.setattr('integration.prepare_restore_target.os.geteuid',lambda:501)
    with pytest.raises(ValueError,match='administrator'):prepare({'job_id':17,'request_id':'12345678-1234-1234-1234-123456789abc'})


def test_helper_rejects_injected_destination_and_missing_approval(monkeypatch,tmp_path):
    import integration.prepare_restore_target as helper
    monkeypatch.setattr(helper.os,'geteuid',lambda:0)
    monkeypatch.setattr(helper,'SCOPE',tmp_path/'absent-scope')
    with pytest.raises(ValueError,match='Unexpected'):prepare({'job_id':17,'request_id':'12345678-1234-1234-1234-123456789abc','destination':'/etc'})
    with pytest.raises(ValueError,match='not enabled'):prepare({'job_id':17,'request_id':'12345678-1234-1234-1234-123456789abc'})
    assert not list(tmp_path.iterdir())


def test_console_json_parser_skips_handshake_text():
    assert rpc_objects('Connected\n{"jsonrpc":"2.0","result":{"api":2}}.command\n{"jsonrpc":"2.0","result":{"jobs":[]}}')[-1]['result']=={'jobs':[]}


def test_transport_disabled_before_ssh(monkeypatch):
    import backend.restore_target as transport
    monkeypatch.setattr(transport,'dotenv_values',lambda path:{})
    monkeypatch.setattr(transport.subprocess,'run',lambda *args,**kwargs:pytest.fail('SSH must remain disabled'))
    with pytest.raises(ValueError,match='disabled'):
        transport.prepare_target(17,'12345678-1234-1234-1234-123456789abc')


def test_helper_rejects_noncanonical_uuid(monkeypatch):
    import integration.prepare_restore_target as helper
    monkeypatch.setattr(helper.os,'geteuid',lambda:0)
    with pytest.raises(ValueError,match='canonical'):
        prepare({'job_id':17,'request_id':'12345678123412341234123456789abc'})


def test_receipt_validation_requires_root_and_exact_source(monkeypatch,tmp_path):
    import importlib.util,json,sys
    from types import SimpleNamespace
    from fastapi import FastAPI,HTTPException
    from uuid import UUID
    monkeypatch.setitem(sys.modules,'bareos_restapi',SimpleNamespace(app=FastAPI(),get_current_user=lambda:None))
    monkeypatch.setitem(sys.modules,'backupcenter_extension',SimpleNamespace(call=lambda *a:None,recovery=lambda *a:None))
    spec=importlib.util.spec_from_file_location('receipt_review',__import__('pathlib').Path(__file__).resolve().parents[2]/'integration/backupcenter_restore.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    receipts=tmp_path/'receipts';receipts.mkdir(mode=0o750)
    monkeypatch.setattr(module,'RECEIPTS',receipts)
    # Simulate root metadata only for local temporary test files.
    original=module.os.fstat
    monkeypatch.setattr(module.os,'fstat',lambda fd:SimpleNamespace(st_uid=0,st_mode=original(fd).st_mode,st_size=original(fd).st_size))
    monkeypatch.setattr(type(receipts),'stat',lambda path,*a,**kw:SimpleNamespace(st_uid=0,st_mode=0o40750))
    request=UUID('12345678-1234-1234-1234-123456789abc')
    plan={'job':'VM-Test','destination':'/mnt/bareos-smb/backupcenter-restore-tests/'+str(request)}
    file=receipts/(str(request)+'.json')
    data={'prepared':True,'requestId':str(request),'sourceJobId':17,**plan}
    file.write_text(json.dumps(data));file.chmod(0o640)
    module.validate_receipt(plan,17,request)
    file.write_text(json.dumps({**data,'sourceJobId':18}))
    with pytest.raises(HTTPException) as error:module.validate_receipt(plan,17,request)
    assert error.value.status_code==409
    file.write_text(json.dumps(data));file.chmod(0o666)
    with pytest.raises(HTTPException):module.validate_receipt(plan,17,request)
