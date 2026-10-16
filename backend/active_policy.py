"""Contract for managed active-policy and per-job scheduling."""
import hashlib
import json
import math
import re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

DAY_NAMES=["mon","tue","wed","thu","fri","sat","sun"]
ORDINAL_NAMES={1:"1st",2:"2nd",3:"3rd",4:"4th",5:"5th"}

def _sorted_unique(values,maximum):
    if any(isinstance(n,bool) or n<1 or n>maximum for n in values) or len(set(values))!=len(values):raise ValueError("Choose unique valid calendar days.")
    return sorted(values)

def _duration_seconds(start,end):
    sh,sm=map(int,start.split(':'));eh,em=map(int,end.split(':'))
    return (eh*60+em)-(sh*60+sm)

def _utc(time_wita):
    hour,minute=map(int,time_wita.split(':'))
    return f"{hour-8:02d}:{minute:02d}"

def _time_slots(start,end,every_hours):
    slots=[_utc(start)]
    if not end or every_hours is None:return slots
    total=_duration_seconds(start,end)
    minutes=every_hours*60
    current=minutes
    while current<=total:
        hour,minute=map(int,start.split(':'))
        next_minutes=hour*60+minute+current
        slots.append(f"{((next_minutes//60)-8)%24:02d}:{next_minutes%60:02d}")
        current+=minutes
    return slots

class AfterJobDependency(BaseModel):
    model_config=ConfigDict(extra="forbid")
    source_job:str
    on_failure:Literal["skip","run_anyway"]="skip"
    level:Literal["configured","full","incremental"]="configured"

class ScheduleCalendar(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mode:Literal["daily","weekly","monthly","monthly_ordinal"]="daily"
    weekdays:list[int]=Field(default_factory=lambda:list(range(1,8)),min_length=1,max_length=7)
    monthdays:list[int]=Field(default_factory=lambda:list(range(1,32)),min_length=1,max_length=31)
    full_mode:Literal["monthdays","weekly","ordinal"]="monthdays"
    full_days:list[int]=Field(default_factory=lambda:[1,15],min_length=1,max_length=31)
    full_weekday:int=Field(default=7,ge=1,le=7)
    ordinal_week:int=Field(default=4,ge=1,le=5)
    ordinal_weekday:int=Field(default=6,ge=1,le=7)
    interval_hours:int|None=Field(default=None,ge=1,le=12)
    @model_validator(mode="after")
    def valid_calendar(self):
        self.weekdays=_sorted_unique(self.weekdays,7)
        self.monthdays=_sorted_unique(self.monthdays,31)
        self.full_days=_sorted_unique(self.full_days,31)
        if self.mode=="weekly" and (self.full_mode!="weekly" or self.full_weekday not in self.weekdays):raise ValueError("Selected weekdays require a weekly Full on one of those days.")
        if self.mode=="monthly" and (self.full_mode!="monthdays" or not set(self.full_days)<=set(self.monthdays)):raise ValueError("Monthly Full dates must be included in the scheduled dates.")
        if self.mode=="monthly" and not any(n<=28 for n in self.full_days):raise ValueError("Include a Full date available in every month (1–28).")
        if self.mode=="monthly_ordinal" and self.full_mode!="ordinal":raise ValueError("Ordinal monthly schedules use their own Full cadence.")
        return self
    def minimum_volumes(self,retention):
        if self.mode=="monthly_ordinal":gap=28
        elif self.full_mode=="weekly":gap=7
        else:
            days=self.full_days
            gap=min([b-a for a,b in zip(days,days[1:])]+[31-days[-1]+days[0]])
        return max(6,math.ceil(retention/gap)+3)

class ActivePolicy(BaseModel):
    model_config=ConfigDict(extra="forbid")
    jobs:list[str]=Field(min_length=1,max_length=25)
    time_wita:str=Field(pattern=r"^(21|22|23):[0-5][0-9]$")
    retention_days:int=Field(ge=30,le=3650)
    maximum_volumes:int=Field(ge=6,le=1000)
    automatic:bool=True
    trigger_mode:Literal["calendar","after_job"]="calendar"
    calendar:ScheduleCalendar|None=None
    after_job:AfterJobDependency|None=None
    window_end_wita:str|None=Field(default=None,pattern=r"^(21|22|23):[0-5][0-9]$")
    retry_count:int=Field(default=0,ge=0,le=10)
    retry_interval_minutes:int=Field(default=30,ge=5,le=1440)
    @model_validator(mode="after")
    def consistent(self):
        if len(self.jobs)!=len(set(self.jobs)):raise ValueError("Select each job once.")
        if self.time_wita=="21:00":raise ValueError("Choose a time after 21:00 WITA.")
        if self.window_end_wita is not None and _duration_seconds(self.time_wita,self.window_end_wita)<=0:raise ValueError("Backup window end must be later than the start time.")
        if self.trigger_mode=="after_job":
            if self.after_job is None:raise ValueError("Choose the job that this job should follow.")
            if len(self.jobs)!=1 or self.after_job.source_job in self.jobs:raise ValueError("After-job scheduling requires one job and it cannot follow itself.")
            if self.calendar is not None:raise ValueError("After-job scheduling does not use a calendar.")
            if not self.automatic:raise ValueError("After-job scheduling requires Automatic schedule enabled.")
        elif self.after_job is not None:raise ValueError("After-job options require after-job scheduling.")
        if self.window_end_wita is not None and self.trigger_mode=="calendar" and (self.calendar is None or self.calendar.interval_hours is None):raise ValueError("Backup window end currently requires an hourly interval calendar.")
        if self.calendar and self.calendar.interval_hours is not None and self.window_end_wita is None:raise ValueError("Hourly intervals require a backup window end time.")
        reserve=self.calendar.minimum_volumes(self.retention_days) if self.calendar else math.ceil(self.retention_days/14)+3
        if self.maximum_volumes<reserve:raise ValueError("Increase maximum volumes to cover retained Full chains and a safety reserve.")
        self.jobs=sorted(self.jobs)
        return self

def schedule(name,time_wita,automatic):
    utc=_utc(time_wita)
    return 'Schedule {\n Name = '+name+'\n Enabled = '+('yes' if automatic else 'no')+'\n Run = Level=Full on 1 at '+utc+'\n Run = Level=Full on 15 at '+utc+'\n Run = Level=Incremental on 2-14 at '+utc+'\n Run = Level=Incremental on 16-31 at '+utc+'\n}\n'

def calendar_schedule(name,time_wita,automatic,calendar=None,window_end_wita=None):
    if calendar is None:return schedule(name,time_wita,automatic)
    c=ScheduleCalendar(**calendar) if isinstance(calendar,dict) else calendar
    slots=_time_slots(time_wita,window_end_wita,c.interval_hours)
    rules=[]
    if c.mode=="monthly_ordinal":
        for i,utc in enumerate(slots):rules.append(f" Run = Level={'Full' if i==0 else 'Incremental'} {ORDINAL_NAMES[c.ordinal_week]} {DAY_NAMES[c.ordinal_weekday-1]} at {utc}")
    elif c.full_mode=="weekly":
        for day in (c.weekdays if c.mode=="weekly" else range(1,8)):
            for i,utc in enumerate(slots):rules.append(f" Run = Level={'Full' if day==c.full_weekday and i==0 else 'Incremental'} {DAY_NAMES[day-1]} at {utc}")
    else:
        for day in (c.monthdays if c.mode=="monthly" else range(1,32)):
            for i,utc in enumerate(slots):rules.append(f" Run = Level={'Full' if day in c.full_days and i==0 else 'Incremental'} on {day} at {utc}")
    return '# BackupCenter schedule: '+json.dumps({"calendar":c.model_dump(),"windowEndWita":window_end_wita},sort_keys=True,separators=(',',':'))+'\n# BackupCenter calendar: '+json.dumps(c.model_dump(),sort_keys=True,separators=(',',':'))+'\nSchedule {\n Name = '+name+'\n Enabled = '+('yes' if automatic else 'no')+'\n'+'\n'.join(rules)+'\n}\n'

def _wita(rule, default="21:30"):
    match = re.search(r"\bat (\d{2}):(\d{2})\b", str(rule))
    if not match:
        return default
    hour = (int(match.group(1)) + 8) % 24
    return f"{hour:02d}:{match.group(2)}"

def current_jobs(snapshot, managed_jobs):
    pools = {row.get("name"): row for row in snapshot.get("pools", []) if isinstance(row, dict)}
    schedules = {row.get("name"): row for row in snapshot.get("schedules", []) if isinstance(row, dict)}
    rows = []
    for job in snapshot.get("jobs", []):
        if job.get("name") not in managed_jobs:
            continue
        schedule_name = job.get("schedule") or "Manual"
        automatic = schedule_name != "Manual"
        schedule_rules = schedules.get(schedule_name, {}).get("rules", [])
        time_wita = _wita(schedule_rules[0] if schedule_rules else None)
        pool = pools.get(job.get("pool"), {})
        rows.append({
            "job": job["name"],
            "timeWita": time_wita,
            "automatic": automatic,
            "retentionDays": int(pool.get("retentionDays") or 30),
            "maximumVolumes": int(pool.get("maxVolumes") or 6),
            "configurationVerified": False,
            "unverifiedFields": ["triggerMode", "afterJob", "windowEndWita", "retryCount", "retryIntervalMinutes"],
            "triggerMode": "calendar",
            "afterJob": None,
            "windowEndWita": None,
            "retryCount": 0,
            "retryIntervalMinutes": 30,
        })
    return sorted(rows, key=lambda row: row["job"])

def preview_payload(definition):
    body = definition.model_dump()
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {
        "definition": body,
        "reviewDigest": digest,
        "existingVolumePolicy": "Existing volumes retain their own minimum. Complete-chain cleanup uses the longer Pool/Volume retention and preserves the latest successful Full.",
        "doesNotRun": "No backup or cleanup is run.",
    }

def patch_retention(source):
    if 'poolretention' in source:return source
    a=" cutoff=now-datetime.timedelta(days=30);jobs=";assert source.count(a)==1;source=source.replace(a,' jobs=')
    a="  vm=m['pool'];name=m['volumename']";assert source.count(a)==1;source=source.replace(a,a+"\n  cutoff=now-datetime.timedelta(seconds=max(int(m.get('poolretention',2592000)),int(m.get('volretention',2592000))))")
    a='m.lastwritten,m.poolid,p.name AS pool';assert source.count(a)==1;return source.replace(a,'m.lastwritten,m.poolid,m.volretention,p.volretention AS poolretention,p.name AS pool')
