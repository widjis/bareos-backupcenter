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
        assert response.json()['jobs']==[{
            'job':'VMware-PNET',
            'timeWita':'22:15',
            'automatic':True,
            'retentionDays':45,
            'maximumVolumes':8,
            'configurationVerified':False,
            'unverifiedFields':['triggerMode','afterJob','windowEndWita','retryCount','retryIntervalMinutes'],
            'triggerMode':'calendar',
            'afterJob':None,
            'windowEndWita':None,
            'retryCount':0,
            'retryIntervalMinutes':30,
        }]


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


def test_active_policy_preview_falls_back_locally_when_helper_contract_is_older(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as module
    monkeypatch.setattr('backend.auth.session_user',lambda _:{'username':'admin','role':'Admin'})
    class FakeGateway:
        values={}
    monkeypatch.setattr(module,'gateway',lambda:FakeGateway())
    monkeypatch.setattr('backend.policy_target.invoke',lambda body: (_ for _ in ()).throw(ValueError('5 validation errors for ActivePolicy\ntrigger_mode\n  Extra inputs are not permitted [type=extra_forbidden]')))
    with TestClient(module.app) as client:
        response=client.post('/api/policies/active/preview',headers={'Origin':'http://127.0.0.1:3000','X-Backup-Center-Action':'confirmed'},json={'definition':definition()})
        assert response.status_code==200
        body=response.json()
        assert body['definition']['trigger_mode']=='calendar'
        assert len(body['reviewDigest'])==64


def test_custom_daily_full_dates_generate_disjoint_native_runs():
    from backend.active_policy import ScheduleCalendar,calendar_schedule
    c=ScheduleCalendar(full_days=[5,20])
    p=ActivePolicy(**definition(calendar=c.model_dump()))
    text=calendar_schedule('BC-Test','21:30',True,p.calendar)
    assert 'Level=Full on 5 at 13:30' in text
    assert 'Level=Full on 20 at 13:30' in text
    assert 'Level=Incremental on 1 at 13:30' in text
    assert len([r for r in text.splitlines() if ' Run =' in r])==31


def test_weekly_run_and_full_selection_are_separate():
    from backend.active_policy import ScheduleCalendar,calendar_schedule
    c=ScheduleCalendar(mode='weekly',weekdays=[1,3,5],full_mode='weekly',full_weekday=5)
    text=calendar_schedule('BC-Test','23:59',True,c)
    assert 'Level=Full fri at 15:59' in text and 'Level=Incremental mon at 15:59' in text
    assert 'tue at' not in text
    with pytest.raises(ValidationError):ActivePolicy(**definition(calendar=c.model_dump()))
    assert ActivePolicy(**definition(calendar=c.model_dump(),maximum_volumes=8))


def test_monthly_dates_and_short_month_full_are_validated():
    from backend.active_policy import ScheduleCalendar,calendar_schedule
    c=ScheduleCalendar(mode='monthly',monthdays=[1,10,20,31],full_days=[1,20])
    text=calendar_schedule('BC-Test','22:00',False,c)
    assert 'Level=Incremental on 31 at 14:00' in text and 'Enabled = no' in text
    assert len([r for r in text.splitlines() if ' Run =' in r])==4
    for kw in [dict(mode='monthly',monthdays=[31],full_days=[31]),dict(weekdays=[0]),dict(full_days=[1,1]),dict(mode='weekly',full_mode='weekly',weekdays=[1],full_weekday=7)]:
        with pytest.raises(ValidationError):ScheduleCalendar(**kw)

def test_interval_and_ordinal_schedules_generate_expected_runs():
    from backend.active_policy import ScheduleCalendar,calendar_schedule
    daily=ScheduleCalendar(full_days=[5],interval_hours=1)
    text=calendar_schedule('BC-Test','21:30',True,daily,'23:30')
    assert 'Level=Full on 5 at 13:30' in text
    assert 'Level=Incremental on 5 at 14:30' in text
    assert 'Level=Incremental on 5 at 15:30' in text
    ordinal=ScheduleCalendar(mode='monthly_ordinal',full_mode='ordinal',ordinal_week=4,ordinal_weekday=6)
    text=calendar_schedule('BC-Test','22:15',True,ordinal)
    assert 'Level=Full 4th sat at 14:15' in text

def test_after_job_requires_single_non_self_job_and_window_order():
    from backend.active_policy import AfterJobDependency
    valid=ActivePolicy(**definition(trigger_mode='after_job',calendar=None,after_job=AfterJobDependency(source_job='VMware-MTIMRWKF01').model_dump(),window_end_wita='23:30'))
    assert valid.after_job and valid.after_job.source_job=='VMware-MTIMRWKF01'
    for kw in [
        dict(trigger_mode='after_job',calendar=None,after_job={'source_job':'VMware-PNET'}),
        dict(trigger_mode='after_job',calendar=None),
        dict(trigger_mode='after_job',calendar=None,after_job={'source_job':'VMware-MTIMRWKF01'},automatic=False),
        dict(window_end_wita='21:15'),
        dict(window_end_wita='23:30'),
        dict(calendar={'mode':'daily','full_mode':'monthdays','full_days':[1,15],'weekdays':[1,2,3,4,5,6,7],'monthdays':list(range(1,32)),'full_weekday':7,'ordinal_week':4,'ordinal_weekday':6,'interval_hours':1}),
    ]:
        with pytest.raises(ValidationError):ActivePolicy(**definition(**kw))
