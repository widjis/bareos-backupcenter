"""Deterministic onboarding previews and dry-run apply; never writes server config."""
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


def script_review(changes, baseline_jobs):
    baseline=sorted({str(job) for job in baseline_jobs if isinstance(job,str) and job})
    additions=[]
    seen=set()
    for change in changes:
        job=change["job"]
        if job in baseline or job in seen:
            continue
        seen.add(job)
        additions.append({
            "inventoryId": change["inventoryId"],
            "name": change["name"],
            "instanceUuid": change["instanceUuid"],
            "job": job,
            "prepareAllowlist": {
                "script": "prepare-vm-backup",
                "action": "Add generated job name to the reviewed VM preparation allowlist.",
                "entry": job,
            },
            "retentionAllowlist": {
                "script": "chain-retention",
                "action": "Add generated job name to the reviewed retention planner allowlist.",
                "entry": job,
            },
        })
    return {
        "required": bool(additions),
        "baselineJobs": baseline,
        "baselineCount": len(baseline),
        "additions": additions,
        "message": "Preparation and retention script allowlists must be extended through reviewed provisioning before any live apply."
        if additions
        else "No new preparation or retention allowlist entries are required for this selection.",
    }


def preview(vms, storage, policy=None, baseline_jobs=None, live_uuids=()):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}",storage.get("name", "")):
        raise ValueError("Select a safely named existing Storage resource.")
    if storage.get("mediaType")!="SMBFile" or not storage.get("enabled"):
        raise ValueError("This preview requires the existing enabled shared SMBFile resource.")
    if live_uuids and any(vm.get("instanceUuid") in live_uuids for vm in vms):
        if len(vms)!=1 or vms[0].get("instanceUuid") not in live_uuids or policy:
            raise ValueError("Live pilot onboarding requires one approved VM and the existing fixed policy.")
        vm=vms[0]
        if vm.get("association")!="Unassigned" or vm.get("template"):
            raise ValueError("The approved VM is already assigned or is a template.")
        from integration.onboarding_contract import build
        bundle=build(vm["instanceUuid"],vm["name"])
        change={"inventoryId":vm["id"],"instanceUuid":vm["instanceUuid"],"name":vm["name"],"job":bundle["job"],"fileset":bundle["fileset"],"pool":bundle["pool"],"storage":bundle["storage"],"configuration":"\n".join(bundle["files"].values()),"state":"Review before live apply"}
        review=script_review([change],baseline_jobs or [])
        for addition in review["additions"]:
            addition["prepareAllowlist"]["entry"]=vm["name"]
            addition["retentionAllowlist"].update(entry=vm["name"],script="retire-vm-chains.py",action="Add VM label and explicit Pool/Job SQL mappings to the chain-retention planner.")
        return {"mode":"live","simulationOnly":False,"changes":[change],"applyEnabled":True,"configurationDigest":bundle["digest"],"policy":{"name":"Existing fixed VMware policy","retentionDays":30,"maximumVolumes":6,"schedule":"Full on 1/15; Incremental other days; 21:30 UTC+8; serial"},"policyId":None,"policyRevision":0,"blockers":["Creates the approved VM folder and root-owned resources after syntax validation.","Preserves VM power state. No first backup is started by Apply; use Run now afterwards."],"sharedImpact":"Creates a dedicated VM folder/device/pool on the existing SMB mount. Extends root-owned preparation/retention mappings; never changes their permissions.","scriptReview":review}
    retention=policy["definition"]["retention_days"] if policy else 30
    maximum=policy["definition"]["maximum_volumes"] if policy else 6
    if not 1<=len(vms)<=25:raise ValueError("Select between one and 25 VMs.")
    changes=[]
    identities=set()
    for vm in vms:
        uid=vm.get("instanceUuid")
        try:canonical=str(UUID(uid))
        except (ValueError,TypeError,AttributeError):raise ValueError("VM instance UUID is missing or invalid.")
        if uid!=canonical:raise ValueError("VM instance UUID must be canonical.")
        if canonical in identities:raise ValueError("Duplicate VM identity in enrollment selection.")
        identities.add(canonical)
        if vm.get("template"):raise ValueError("Templates are not eligible for this onboarding flow.")
        if vm.get("association")!="Unassigned":raise ValueError("Review existing or ambiguous assignments before enrollment.")
        name="BC-"+re.sub(r"[^A-Za-z0-9_.-]","-",vm["name"])[:70]+"-"+uid.replace("-", "")
        fileset=name+"-FS"
        pool=name+"-Pool"
        definition=(f'FileSet {{\n  Name = "{fileset}"\n  Include {{\n    Plugin = "python3:module_path=/opt/bareos/25.1.1/lib/bareos/plugins:module_name=bareos-fd-vmware:uuid={uid}:enable_cbt=yes:config_file=/etc/bareos/vmware-plugin.ini"\n  }}\n}}\n'
            +f'Pool {{\n  Name = "{pool}"\n  Pool Type = Backup\n  Storage = "{storage["name"]}"\n  Recycle = yes\n  AutoPrune = no\n  Volume Retention = {retention} days\n  Maximum Volumes = {maximum}\n  Label Format = "{name}-"\n}}\n'
            +f'Job {{\n  Name = "{name}"\n  Type = Backup\n  Client = "bareos-fd"\n  FileSet = "{fileset}"\n  Storage = "{storage["name"]}"\n  Pool = "{pool}"\n  Messages = Standard\n  Level = Incremental\n  Enabled = no\n}}\n')
        changes.append({"inventoryId":vm["id"],"instanceUuid":uid,"name":vm["name"],"job":name,"fileset":fileset,"pool":pool,"storage":storage["name"],"configuration":definition,"state":"Preview only"})
    review=script_review(changes,baseline_jobs or [])
    return {"changes":changes,"applyEnabled":True,"policy":{"name":policy["name"] if policy else "Existing-environment baseline (proposal)","retentionDays":retention,"maximumVolumes":maximum,"schedule":"Disabled until reviewed scheduling and script mappings are installed"},"blockers":["This apply path stages a durable rehearsal only; live Bareos configuration load remains disabled.","Preparation and retention mappings must still be updated before live onboarding.","Configuration reload and first backup acceptance remain separate operator-approved steps.","No schedule or first backup is created by this preview."],"policyId":str(policy["id"]) if policy else None,"policyRevision":policy["revision"] if policy else None,"sharedImpact":"Reuses existing SMBFile storage; creates no new physical repository or Storage Daemon device.","scriptReview":review}


def rehearse(plan):
    if not plan.get("changes"):
        raise ValueError("Provisioning rehearsal requires at least one generated change.")
    created=datetime.now(timezone.utc).isoformat()
    digest=hashlib.sha256()
    files=[]
    # Temporary local fixtures prove the generated payload is self-consistent without
    # touching the Bareos server or leaving reusable files behind.
    with tempfile.TemporaryDirectory(prefix="backupcenter-provisioning-") as root:
        base=Path(root)
        for index,change in enumerate(plan["changes"],start=1):
            name=re.sub(r"[^A-Za-z0-9_.-]","-",change["job"])[:120] or f"change-{index}"
            target=base / f"{index:02d}-{name}.conf"
            text=change["configuration"]
            target.write_text(text,encoding="utf-8")
            digest.update(target.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(text.encode("utf-8"))
            files.append({"name":target.name,"bytes":len(text.encode("utf-8")),"job":change["job"],"inventoryId":change["inventoryId"]})
        manifest={"generatedAt":created,"vmCount":len(plan["changes"]),"files":files,"policy":plan.get("policy"),"sharedImpact":plan.get("sharedImpact"),"simulationOnly":True}
        payload=json.dumps(manifest,sort_keys=True).encode("utf-8")
        digest.update(payload)
        return {"generatedAt":created,"vmCount":len(plan["changes"]),"fileCount":len(files),"sha256":digest.hexdigest(),"manifest":manifest,"message":"Provisioning rehearsal completed. Generated temporary local fixtures only; no Bareos configuration was loaded."}
