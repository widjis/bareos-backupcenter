"""Pure direct-VM restore review; never composes or sends a console command."""
import hashlib,json,re
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator

class VMRestoreDestination(BaseModel):
    model_config=ConfigDict(extra="forbid",str_strip_whitespace=True)
    vm_name:str=Field(min_length=1,max_length=80)
    datacenter:str=Field(min_length=1,max_length=128)
    folder:str=Field(min_length=1,max_length=256)
    host:str=Field(min_length=1,max_length=253)
    datastore:str=Field(min_length=1,max_length=128)
    power:Literal["off"]="off"
    network:Literal["disconnected"]="disconnected"
    overwrite:Literal["Never"]="Never"

    @field_validator("vm_name","datacenter","host","datastore")
    @classmethod
    def resource_name(cls,value):
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_. -]*",value):
            raise ValueError("Use letters, numbers, spaces, dot, hyphen or underscore; start with a letter, number or underscore.")
        return value

    @field_validator("folder")
    @classmethod
    def folder_path(cls,value):
        if not value.startswith("/") or "//" in value or any(p in (".","..") for p in value.split("/")) or not re.fullmatch(r"/[A-Za-z0-9_ ./-]*",value):
            raise ValueError("Use an absolute VMware folder path without traversal, for example /RestoreTests.")
        return value

def build_vm_restore_plan(recovery,destination,plugin):
    blockers=list(recovery.get("blockers",[]))
    if not recovery.get("engineResolved") or not recovery.get("jobIds"):
        blockers.append("The Director must resolve a complete backup chain.")
    if "bareos-fd-vmware" not in plugin:
        raise ValueError("Only configured VMware plugin backups support this review.")
    uuid_source=bool(re.search(r"(?:^|:)\s*uuid=",plugin))
    if uuid_source:
        blockers.append("This backup uses UUID addressing. Restore to a different VM requires a verified UUID compatibility path before execution.")
    blockers.extend(["Destination host, datastore, folder, capacity and permissions have not been verified against live vCenter.","Direct VMware execution and disconnected-network enforcement are not implemented. This review does not create a VM."])
    body={"sourceJobId":recovery["sourceJobId"],"jobIds":recovery["jobIds"],"destination":destination.model_dump(),"mode":"vmware-new-vm"}
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {**body,"reviewDigest":digest,"dispatchEnabled":False,"targetVerified":False,"uuidSource":uuid_source,"blockers":list(dict.fromkeys(blockers)),"requiredMedia":sorted({m["name"] for r in recovery.get("chain",[]) for m in r.get("media",[])}),"state":"Review only"}
