"""VMware recovery inspection; no implicit restore dispatch."""
from backend.app import number, timestamp


def normalize_recovery(source, files, volumes):
    chain=[]
    blockers=[]
    catalog={v["name"]:v for v in volumes}
    for row in source.get("chain",[]):
        names=sorted({m.get("volumename") for m in row.get("media",[]) if m.get("volumename")})
        pruned=bool(number(row.get("purgedfiles")))
        if pruned:blockers.append("File metadata was pruned for JobId "+str(row.get("jobid"))+".")
        if not names:blockers.append("Media mapping is missing for JobId "+str(row.get("jobid"))+".")
        if row.get("mediaMappingsTruncated"):blockers.append("Media mapping exceeds the inspection limit.")
        media=[]
        for name in names:
            volume=catalog.get(name)
            unavailable=not volume or volume.get("status") in ("Purged","Error","Disabled")
            if unavailable:blockers.append("Cannot confirm usable Catalog media: "+name+".")
            media.append({"name":name,"status":volume.get("status") if volume else "Not in retrieved Catalog window","readabilityVerified":False})
        chain.append({"jobId":number(row.get("jobid")),"job":row.get("name"),"level":{"F":"Full","I":"Incremental","D":"Differential"}.get(row.get("level"),"Unknown"),"status":"Warning" if row.get("jobstatus")=="W" else "Succeeded","started":timestamp(row.get("starttime")),"ended":timestamp(row.get("endtime")),"bytes":number(row.get("jobbytes")),"metadataPruned":pruned,"media":media})
    if not chain or not any(r["level"]=="Full" for r in chain):blockers.append("A Full backup baseline is not available.")
    items=[]
    for row in files.get("filenames",[])[:2000]:
        name=str(row.get("filename",""))
        if name.endswith(".vmdk") or ".vmdk+" in name:kind="Virtual disk backup"
        elif name.endswith(".nvram"):kind="VM firmware state"
        else:kind="VM backup item"
        items.append({"path":name,"kind":kind})
    return {"sourceJobId":source["sourceJobId"],"jobIds":source["jobIds"],"chain":chain,"items":items,"itemLimit":2000,"itemTotal":number(files.get("totalItems")),"engineResolved":bool(source.get("engineResolved")),"blockers":list(dict.fromkeys(blockers)),"mediaReadableVerified":False,"restoreVerified":False,"dispatchEnabled":False,"modes":[{"id":"vm-disks-isolated","name":"Export VMware disks to an isolated directory","state":"Implementation pending","destinationPrefix":"/mnt/bareos-smb/backupcenter-restore-tests/","overwrite":"Never"}],"unsupported":["Guest-file recovery","Instant VM recovery","Application-item recovery","Restore to original VM"]}
