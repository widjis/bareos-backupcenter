"""Contract for the existing twice-monthly VMware policy."""
import math
from pydantic import BaseModel,ConfigDict,Field,model_validator
class ActivePolicy(BaseModel):
    model_config=ConfigDict(extra="forbid")
    jobs:list[str]=Field(min_length=1,max_length=25)
    time_wita:str=Field(pattern=r"^(21|22|23):[0-5][0-9]$")
    retention_days:int=Field(ge=30,le=3650)
    maximum_volumes:int=Field(ge=6,le=1000)
    automatic:bool=True
    @model_validator(mode="after")
    def consistent(self):
        if len(self.jobs)!=len(set(self.jobs)):raise ValueError("Select each job once.")
        if self.time_wita=="21:00":raise ValueError("Choose a time after 21:00 WITA.")
        if self.maximum_volumes<math.ceil(self.retention_days/14)+3:raise ValueError("Increase maximum volumes to cover retained Full chains and a safety reserve.")
        self.jobs=sorted(self.jobs)
        return self

def schedule(name,time_wita,automatic):
    hour,minute=map(int,time_wita.split(':'));utc=f"{hour-8:02d}:{minute:02d}"
    return 'Schedule {\n Name = '+name+'\n Enabled = '+('yes' if automatic else 'no')+'\n Run = Level=Full on 1 at '+utc+'\n Run = Level=Full on 15 at '+utc+'\n Run = Level=Incremental on 2-14 at '+utc+'\n Run = Level=Incremental on 16-31 at '+utc+'\n}\n'

def patch_retention(source):
    if 'poolretention' in source:return source
    a=" cutoff=now-datetime.timedelta(days=30);jobs=";assert source.count(a)==1;source=source.replace(a,' jobs=')
    a="  vm=m['pool'];name=m['volumename']";assert source.count(a)==1;source=source.replace(a,a+"\n  cutoff=now-datetime.timedelta(seconds=max(int(m.get('poolretention',2592000)),int(m.get('volretention',2592000))))")
    a='m.lastwritten,m.poolid,p.name AS pool';assert source.count(a)==1;return source.replace(a,'m.lastwritten,m.poolid,m.volretention,p.volretention AS poolretention,p.name AS pool')
