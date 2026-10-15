from datetime import datetime,timezone
from backend.session_progress import progress

def row(**kw):
    return {"jobid":"27","name":"RestoreFiles","type":"R","jobstatus":"R","starttime":"2026-10-15 07:40:38","endtime":None,"jobbytes":"0","jobfiles":"0","joberrors":"0"}|kw

def test_active_progress_has_no_invented_percentage_or_total():
    p=progress(row(),[{"time":"","text":"Successfully created VM PNET-RESTORE-TEST"}],datetime(2026,10,15,7,41,38,tzinfo=timezone.utc))
    assert p['active'] and p['phase']=='Restoring disks' and p['elapsedSeconds']==60
    assert p['percentage'] is None and p['totalBytes'] is None and p['bytes']==0

def test_warning_is_terminal_and_uses_real_final_counters():
    p=progress(row(jobstatus='W',endtime='2026-10-15 07:42:07',jobbytes='16044756500',jobfiles='3'),[])
    assert not p['active'] and p['phase']=='Completed with warnings' and p['elapsedSeconds']==89
    assert p['bytes']==16044756500 and p['files']==3

def test_failed_canceled_and_log_tail_are_bounded():
    p=progress(row(jobstatus='f'),[{'time':'','text':str(i)} for i in range(150)])
    assert p['phase']=='Failed' and not p['active'] and len(p['lines'])==80
    assert progress(row(jobstatus='A'),[])['phase']=='Canceled'


def test_only_explicit_identity_warning_is_explained_as_identity_change():
    lines=[{'time':'','text':'Warning: UUID old already exists in VM original, restored VM will get new generated UUID'}, {'time':'','text':'Warning: Read timeout during restore'}, {'time':'','text':'Termination: Restore OK -- with warnings'}]
    p=progress(row(jobstatus='W'),lines)
    assert [w['kind'] for w in p['warnings']]==['identity-change','unclassified']
    assert p['status']=='Warning' and p['phase']=='Completed with warnings'
    assert 'needs review' in p['warnings'][1]['explanation']
