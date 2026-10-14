"""Fixed read-only recovery inspection routes on the existing guarded API."""
from fastapi import Depends, HTTPException
from bareos_restapi import app, get_current_user


def call(user, command):
    try:
        result = user.jsonDirector.call(command)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except Exception:
        raise HTTPException(502, "Director recovery inspection unavailable.")


def job(user, job_id):
    rows = call(user, "llist jobid=" + str(job_id)).get("jobs", [])
    if len(rows) != 1:
        raise HTTPException(404, "Catalog session not available.")
    row = rows[0]
    if row.get("type") != "B" or row.get("jobstatus") not in ("T", "W"):
        raise HTTPException(409, "Select a completed backup session.")
    return {key: row.get(key) for key in ("jobid", "name", "clientid", "filesetid", "level", "jobstatus", "starttime", "endtime", "purgedfiles", "jobbytes")}


@app.get("/backupcenter/recovery/{job_id}", tags=["backupcenter-recovery"])
def recovery(job_id: int, current_user=Depends(get_current_user)):
    if job_id < 1 or job_id > 9223372036854775807:
        raise HTTPException(422, "Invalid JobId.")
    source = job(current_user, job_id)
    raw = call(current_user, ".bvfs_get_jobids jobid=" + str(job_id)).get("jobids", [])
    try:
        ids = [int(row["id"]) for row in raw]
    except Exception:
        raise HTTPException(502, "Director returned an invalid dependency chain.")
    if not ids or job_id not in ids or len(ids) > 100 or any(x < 1 or x > 9223372036854775807 for x in ids):
        raise HTTPException(409, "A bounded dependency chain is unavailable.")
    chain = []
    for member in ids:
        item = job(current_user, member)
        if item["clientid"] != source["clientid"] or item["filesetid"] != source["filesetid"]:
            raise HTTPException(409, "Dependency chain contains another source or FileSet.")
        media = call(current_user, "list jobmedia jobid=" + str(member)).get("jobmedia", [])
        item["media"] = [{k: row.get(k) for k in ("volumename", "volumeid", "firstindex", "lastindex", "startfile", "endfile")} for row in media[:500]]
        item["mediaMappingsTruncated"] = len(media) > 500
        chain.append(item)
    return {"sourceJobId": job_id, "jobIds": ids, "chain": chain, "engineResolved": True, "mediaReadableVerified": False, "restoreVerified": False}
