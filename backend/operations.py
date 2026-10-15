"""Single-leader durable dispatcher; never retries a possibly dispatched mutation."""
import asyncio
import re
from contextlib import closing
import httpx
from backend.restore_target import prepare_target
from backend.provisioning import rehearse

ACTIVE = {"R","C","B","F","S","M","s","m","j","c","d","t","p","q","a","i","L"}


async def validate(gateway, client, kind, target):
    if kind != "provision" and not getattr(gateway,"operation_dispatch_enabled",True):
        raise ValueError("Live job operations are deferred; dispatch is disabled.")
    if kind == "run":
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", target):
            raise ValueError("This API safely supports job names containing letters, numbers, dot, hyphen, and underscore only.")
        allowed = getattr(gateway,"operation_jobs",None)
        if allowed is not None and target not in allowed:
            raise ValueError("This job is outside the enabled Run/Cancel scope.")
        data = await gateway.get(client, "/configuration/jobs")
        jobs=data.get("jobs",{})
        row=jobs.get(target) if isinstance(jobs,dict) else next((j for j in jobs if j.get("name")==target),None)
        if not row or row.get("type")!="Backup" or not row.get("enabled"):
            raise ValueError("Select an enabled backup job from the current Director configuration.")
        recent=await gateway.get(client,"/control/jobs?limit=200",{"job":target})
        total=int(recent.get("totalItems",0))
        if total>200:recent=await gateway.get(client,f"/control/jobs?limit=200&offset={total-200}",{"job":target})
        if any(j.get("name")==target and j.get("jobstatus") in ACTIVE for j in recent.get("jobs",[])):
            raise ValueError("This backup job already has an active session. Wait for it to finish or review History.")
    elif kind == "restore":
        if not getattr(gateway,"restore_enabled",False):raise ValueError("Live isolated restore has not been enabled.")
        if not target.isdigit() or int(target)<1:raise ValueError("Select a valid backup JobId.")
        row=await gateway.get(client,"/control/jobs/"+str(int(target)))
        if row.get("name")!=gateway.restore_test_job or row.get("type")!="B" or row.get("jobstatus") not in ("T","W"):
            raise ValueError("Select a completed backup in the explicitly approved test-job scope.")
        chain=await gateway.get(client,"/backupcenter/recovery/"+str(int(target)))
        if not chain.get("chain") or not any(x.get("level")=="F" for x in chain["chain"]):raise ValueError("A Full recovery baseline is required.")
        if any(str(x.get("purgedfiles"))!="0" or not x.get("media") or x.get("mediaMappingsTruncated") for x in chain["chain"]):
            raise ValueError("Complete file and media metadata is required for isolated restore.")
    elif kind == "cancel":
        if not target.isdigit() or int(target)<1:
            raise ValueError("Select a valid active backup JobId.")
        row=await gateway.get(client,"/control/jobs/"+str(int(target)))
        allowed = getattr(gateway,"operation_jobs",None)
        if allowed is not None and row.get("name") not in allowed:
            raise ValueError("This session is outside the enabled Run/Cancel scope.")
        if row.get("type")!="B" or row.get("jobstatus") not in ACTIVE:
            raise ValueError("Only an active backup session can be canceled. Refresh its current status.")
    elif kind == "provision":
        if not re.fullmatch(r"[0-9a-f-]{36}", target):
            raise ValueError("Provisioning rehearsal requires a canonical revision identifier.")
    else:
        raise ValueError("Operation is not supported.")


async def dispatch(gateway, operation):
    store=gateway.store
    if operation["kind"]=="restore" and operation.get("parameters",{}).get("mode")=="vmware-new-vm":
        await dispatch_vm(gateway,operation)
        return
    if operation["kind"] == "provision":
        revision=await asyncio.to_thread(store.provision_revision,operation["target"])
        if not revision:
            await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Failed",None,"Provisioning revision is no longer available.")
            return
        if not await asyncio.to_thread(store.actor_allowed,operation["actor"],"provision"):
            await asyncio.to_thread(store.finish_provisioning,operation["target"],operation["actor"],"Failed",{"message":"Administrator permission was revoked before provisioning rehearsal."})
            await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Failed",None,"Administrator permission was revoked before provisioning rehearsal.")
            return
        live=revision["payload"].get("mode")=="live"
        claimed=await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Dispatching",None,"Applying approved VM configuration." if live else "Running provisioning rehearsal with temporary local fixtures.")
        if not claimed:return
        try:
            if live:
                from backend.onboarding_target import apply_target
                async with gateway.lock:
                    result=await asyncio.to_thread(apply_target,revision["payload"],operation["idempotency_key"])
                gateway.cached_at=float("-inf")
            else:
                result=await asyncio.to_thread(rehearse,revision["payload"])
            await asyncio.to_thread(store.finish_provisioning,operation["target"],operation["actor"],"Validated",result)
            await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Completed",None,result["message"])
        except Exception:
            message="Controlled onboarding did not complete; inspect the server receipt and configuration before retrying." if live else "Provisioning rehearsal failed before any Bareos configuration change."
            if live:
                await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Unknown",None,message)
                return
            await asyncio.to_thread(store.finish_provisioning,operation["target"],operation["actor"],"Failed",{"message":message})
            await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Failed",None,message)
        return
    async with gateway.lock:
        async with httpx.AsyncClient(verify=gateway.context,timeout=15,trust_env=False) as client:
            try:
                await validate(gateway,client,operation["kind"],operation["target"])
                if not await asyncio.to_thread(store.actor_allowed,operation["actor"],operation["kind"]):
                    raise ValueError("Operation permission was revoked; no command was sent.")
            except Exception as exc:
                await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Failed",None,str(exc) if isinstance(exc,ValueError) else "Preflight failed; no job command was sent.")
                return
            # Database commit precedes side effect. Failure here means no dispatch.
            claimed=await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Dispatching",None,"Sending the confirmed request to Bareos.")
            if not claimed:return
            try:
                # Authenticated during preflight; do not resend or renew/retry this mutation.
                headers={"Authorization":"Bearer "+gateway.token}
                if operation["kind"]=="run":
                    control={"job":operation["target"],"comment":"backupcenter-"+str(operation["id"])}
                    level=operation.get("parameters",{}).get("requestedLevel")
                    if level is not None:
                        if level not in ("Full","Incremental"):raise ValueError("Unsupported requested backup level")
                        control["level"]=level
                    response=await client.post(gateway.base+"/control/jobs/run",headers=headers,json={"jobControl":control})
                elif operation["kind"]=="restore":
                    await asyncio.to_thread(prepare_target,int(operation["target"]),str(operation["idempotency_key"]))
                    response=await client.post(gateway.base+"/backupcenter/restore/vm-disks",headers=headers,json={"job_id":int(operation["target"]),"request_id":str(operation["idempotency_key"]),"confirmed":True})
                else:
                    response=await client.put(gateway.base+"/control/jobs/cancel/"+str(int(operation["target"])),headers=headers)
                if 400<=response.status_code<500:
                    await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Failed",None,f"Bareos rejected the request (HTTP {response.status_code}). No automatic retry.")
                    return
                response.raise_for_status()
                data=response.json()
                job_id=data.get("jobid") if operation["kind"] in ("run","restore") and isinstance(data,dict) else operation["job_id"]
                if not isinstance(job_id,int) or isinstance(job_id,bool) or job_id<1:
                    raise ValueError("JobId not confirmed")
                await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Accepted",job_id,"Bareos accepted the request. Waiting for Director session status.")
                gateway.cached_at=float("-inf")
            except Exception:
                # Includes HTTP 500: installed API may have started a job without returning its ID.
                await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Unknown",None,"Delivery outcome is unknown. Check Bareos history before taking further action; this request will not be resent.")


async def reconcile(gateway, operation):
    if not operation["job_id"]:return
    async with gateway.lock:
        async with httpx.AsyncClient(verify=gateway.context,timeout=12,trust_env=False) as client:
            try:
                row=await gateway.get(client,"/control/jobs/"+str(operation["job_id"]))
            except Exception:
                return
    code=row.get("jobstatus")
    from backend.app import session
    outcome=session(row)["status"]
    state=None
    if operation["kind"]=="cancel":
        if code=="A":state="Completed"
        elif code in {"T","W","E","e","f"}:state="Failed"
    else:
        if code in {"T","W"}:state="Completed"
        elif code in {"A","E","e","f"}:state="Failed"
        elif code=="R":state="Running"
    if state=="Completed" and operation.get("parameters",{}).get("mode")=="vmware-new-vm":
        try:
            from backend.direct_restore_target import invoke
            verified=await asyncio.to_thread(invoke,{"action":"verify","request_id":str(operation["idempotency_key"])})
            if not verified.get("isolationVerified"):raise ValueError()
        except Exception:
            await asyncio.to_thread(gateway.store.transition,operation["id"],[operation["state"]],"Failed",operation["job_id"],"Restore ended but VM isolation/identity verification failed. Inspect destination before power on.")
            return
    if state and state!=operation["state"]:
        message=("Cancellation confirmed by Director." if code=="A" and operation["kind"]=="cancel" else ("Job finished before cancellation was confirmed." if operation["kind"]=="cancel" else "Director session status: "+outcome+"."))
        await asyncio.to_thread(gateway.store.transition,operation["id"],[operation["state"]],state,operation["job_id"],message,outcome)
        gateway.cached_at=float("-inf")


async def worker(factory):
    leader=None
    initialized=False
    try:
        while True:
            try:
                gateway=factory()
                if not gateway.store.configured:
                    await asyncio.sleep(3)
                    continue
                if leader is None:
                    leader=await asyncio.to_thread(gateway.store.worker_lock)
                    initialized=False
                if leader is None:
                    await asyncio.sleep(3)
                    continue
                # Verify the leadership connection still exists before processing.
                def alive():
                    with leader.cursor() as cursor:cursor.execute("SELECT 1")
                await asyncio.to_thread(alive)
                if not initialized:
                    await asyncio.to_thread(gateway.store.recover_dispatching)
                    initialized=True
                for operation in await asyncio.to_thread(gateway.store.operations,True):
                    if operation["state"]=="Prepared":await dispatch(gateway,operation)
                    else:await reconcile(gateway,operation)
            except asyncio.CancelledError:
                raise
            except Exception:
                if leader:
                    leader.close()
                    leader=None
                # Safe recovery always marks in-flight dispatches Unknown before another send.
                initialized=False
            await asyncio.sleep(3)
    finally:
        if leader:leader.close()


async def dispatch_vm(gateway,operation):
    from backend.direct_restore_target import invoke
    p=operation["parameters"];store=gateway.store
    try:
        if not gateway.operation_dispatch_enabled or gateway.values.get("BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED")!="1":raise ValueError("Direct VMware restore is disabled.")
        if not await asyncio.to_thread(store.actor_allowed,operation["actor"],"restore"):raise ValueError("Administrator permission was revoked.")
        plan=await asyncio.to_thread(invoke,{"action":"plan","job_id":int(operation["target"]),"destination":p["destination"]})
        if plan.get("reviewDigest")!=p["reviewDigest"] or not plan.get("dispatchEnabled"):raise ValueError("Restore intent changed; review again.")
    except Exception as exc:
        await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Failed",None,str(exc) if isinstance(exc,ValueError) else "Restore preflight unavailable; no job sent.")
        return
    claimed=await asyncio.to_thread(store.transition,operation["id"],["Prepared"],"Dispatching",None,"Sending the confirmed new-VM restore request.")
    if not claimed:return
    try:
        result=await asyncio.to_thread(invoke,{"action":"dispatch","job_id":int(operation["target"]),"destination":p["destination"],"request_id":str(operation["idempotency_key"]),"digest":p["reviewDigest"]})
        job_id=result.get("jobid")
        if not isinstance(job_id,int) or job_id<1:raise ValueError("JobId not confirmed")
        await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Accepted",job_id,"New-VM restore accepted. Waiting for Director and isolation verification.")
        gateway.cached_at=float("-inf")
    except Exception:
        await asyncio.to_thread(store.transition,operation["id"],["Dispatching"],"Unknown",None,"New-VM restore outcome unknown. Reconcile root receipt/Director history; never resend automatically.")
