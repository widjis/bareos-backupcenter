"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders } from "./auth";
import { NativeSelectField } from "./form-controls";
import { useUnsavedDraft } from "./draft-guard";

type Destination = { vm_name: string; datacenter: string; folder: string; host: string; datastore: string };
type Plan = { dispatchEnabled: boolean; state: string; jobIds: number[]; requiredMedia: string[]; blockers: string[]; reviewDigest: string; destination: Destination };
const fields: { key: keyof Destination; label: string; hint: string }[] = [
  { key: "vm_name", label: "New VM name", hint: "PNET-RESTORE-TEST" },
  { key: "datacenter", label: "Destination datacenter", hint: "Exact vCenter name" },
  { key: "folder", label: "Destination VM folder", hint: "/RestoreTests" },
  { key: "host", label: "Destination ESXi host", hint: "Exact host name" },
  { key: "datastore", label: "Destination datastore", hint: "Exact datastore name" },
];
export function VMwareRestorePlan({ jobId, onDirty, onQueued }: { jobId: number; onDirty: (dirty: boolean) => void; onQueued: (operation: Record<string, unknown>) => void }) {
  type DC = { name: string; folders: {path:string}[]; hosts: {name:string; datastores:{name:string; freeBytes:number}[]}[] };
  const [approvedJobs,setApprovedJobs] = useState<string[]>([]);
  const [targets,setTargets] = useState<DC[]>([]), [targetError,setTargetError] = useState("");
  const [targetRetry,setTargetRetry] = useState(0), [targetsLoading,setTargetsLoading] = useState(true);
  const confirm = useRef<HTMLDialogElement>(null), back = useRef<HTMLButtonElement>(null), submit = useRef<HTMLButtonElement>(null);
  const key = useRef(""), lock = useRef(false);
  const [sending,setSending] = useState(false), [sendError,setSendError] = useState("");
  useEffect(() => { const a=new AbortController(); setTargetsLoading(true); setTargetError(""); setTargets([]);
    apiFetch("/api/recovery/vmware/targets",{signal:a.signal}).then(async r => {const x=await r.json();if(!r.ok)throw new Error(typeof x.detail==="string"?x.detail:"Destination inventory unavailable.");if(!a.signal.aborted){setTargets(x.datacenters);setApprovedJobs(x.dispatchScope||[]);}}).catch(e => {if(!a.signal.aborted)setTargetError(e.message);}).finally(() => {if(!a.signal.aborted)setTargetsLoading(false);});return()=>a.abort();
  },[targetRetry]);
  const [draft, setDraft] = useState<Destination>({ vm_name: "", datacenter: "", folder: "/", host: "", datastore: "" });
  const [plan, setPlan] = useState<Plan | null>(null), [error, setError] = useState("");
  const [busy, setBusy] = useState(false), [invalid, setInvalid] = useState<string[]>([]);
  const form = useRef<HTMLFormElement>(null), generation = useRef(0), controller = useRef<AbortController | null>(null);
  const dirty = Boolean(draft.vm_name || draft.datacenter || draft.folder !== "/" || draft.host || draft.datastore);
  useUnsavedDraft(dirty);
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => () => { generation.current++; controller.current?.abort(); }, []);
  function edit(key: keyof Destination, value: string) {
    generation.current++; controller.current?.abort(); setBusy(false); setPlan(null); setError(""); setInvalid([]);
    setDraft((d) => ({ ...d, [key]: value }));
  }
  const dc=targets.find(x=>x.name===draft.datacenter), host=dc?.hosts.find(x=>x.name===draft.host);
  return <section className="policy-form" aria-labelledby="vmware-restore-plan-title">
    <h3 id="vmware-restore-plan-title">Restore as a new VMware VM</h3>
    <p>Review a destination for this recovery point. The new VM must stay powered off with its network disconnected. Existing VMs are never overwritten.</p>
    <p>Choose a live vCenter destination. The restored VM has no network adapters and stays powered off until a separate boot test.</p>
    {!!approvedJobs.length && <p>Enabled source jobs: {approvedJobs.join(", ")}</p>}
    {targetsLoading && <p role="status">Loading VMware destinations…</p>}
    {targetError && <div role="alert"><p>{targetError}</p><button className="button" onClick={()=>setTargetRetry(n=>n+1)}>Retry destinations</button></div>}
    <form ref={form} noValidate onSubmit={async (e) => {
      e.preventDefault(); if (busy) return;
      const missing = fields.filter((f) => !draft[f.key].trim()).map((f) => f.key);
      setInvalid(missing); setPlan(null); setError("");
      if (missing.length) { setError("Complete all destination fields."); form.current?.querySelector<HTMLElement>(`[name="${missing[0]}"], [aria-label="${fields.find(f=>f.key===missing[0])?.label}"]`)?.focus(); return; }
      const version = ++generation.current; const abort = new AbortController(); controller.current = abort; setBusy(true);
      try {
        const response = await apiFetch("/api/recovery/vmware/plan", { method: "POST", headers: actionHeaders, signal: abort.signal,
          body: JSON.stringify({ source_job_id: jobId, destination: { ...draft, power: "off", network: "disconnected", overwrite: "Never" } }) });
        const result = await response.json();
        if (version !== generation.current) return;
        if (!response.ok) {
          if (Array.isArray(result.detail)) {
            const keys = result.detail.map((d: { loc?: string[] }) => d.loc?.at(-1)).filter(Boolean);
            setInvalid(keys); form.current?.querySelector<HTMLElement>(`[name="${keys[0]}"], [aria-label="${fields.find(f=>f.key===keys[0])?.label}"]`)?.focus();
          }
          throw new Error(typeof result.detail === "string" ? result.detail : "Check destination names and use an absolute folder path without traversal.");
        }
        setPlan(result); key.current=crypto.randomUUID();
      } catch (err) { if (version === generation.current && !abort.signal.aborted) setError(err instanceof Error ? err.message : "Restore review unavailable."); }
      finally { if (version === generation.current) setBusy(false); }
    }}>
      <div className="policy-fields">
        <label className="auth-field"><span>New VM name</span><input name="vm_name" value={draft.vm_name} maxLength={80} placeholder="PNET-RESTORE-TEST" aria-invalid={invalid.includes("vm_name")} aria-describedby={invalid.includes("vm_name")?"vmware-plan-error":undefined} onChange={e=>edit("vm_name",e.target.value)} /></label>
        <NativeSelectField label="Destination datacenter" value={draft.datacenter} disabled={targetsLoading||!targets.length} invalid={invalid.includes("datacenter")} describedBy={invalid.includes("datacenter")?"vmware-plan-error":undefined} options={[{value:"",label:"Select datacenter"},...targets.map(x=>({value:x.name,label:x.name}))]} onChange={v=>{edit("datacenter",v);setDraft(d=>({...d,folder:"/",host:"",datastore:""}));}} />
        <NativeSelectField label="Destination VM folder" value={draft.folder} disabled={!dc} invalid={invalid.includes("folder")} describedBy={invalid.includes("folder")?"vmware-plan-error":undefined} options={(dc?.folders||[{path:"/"}]).map(x=>({value:x.path,label:x.path}))} onChange={v=>edit("folder",v)} />
        <NativeSelectField label="Destination ESXi host" value={draft.host} disabled={!dc} invalid={invalid.includes("host")} describedBy={invalid.includes("host")?"vmware-plan-error":undefined} options={[{value:"",label:"Select host"},...(dc?.hosts||[]).map(x=>({value:x.name,label:x.name}))]} onChange={v=>{edit("host",v);setDraft(d=>({...d,datastore:""}));}} />
        <NativeSelectField label="Destination datastore" value={draft.datastore} disabled={!host} invalid={invalid.includes("datastore")} describedBy={invalid.includes("datastore")?"vmware-plan-error":undefined} options={[{value:"",label:"Select datastore"},...(host?.datastores||[]).map(x=>({value:x.name,label:x.name+" · "+(x.freeBytes/1024**3).toFixed(0)+" GiB free"}))]} onChange={v=>edit("datastore",v)} />
      </div>
      <p>Power: Off · Network: Disconnected · Overwrite: Never</p>
      <button className="button" disabled={busy || targetsLoading || !!targetError} aria-busy={busy} type="submit">{busy ? "Reviewing destination…" : "Review VMware restore"}</button>
      {busy && <p role="status">Checking backup dependencies and source configuration…</p>}
      {error && <p id="vmware-plan-error" role="alert">{error}</p>}
    </form>
    {plan && <div className="info-note" role="status"><div>
      <h4>VMware restore review</h4>
      <p>{plan.destination.vm_name} → {plan.destination.datacenter}{plan.destination.folder} · {plan.destination.host} · {plan.destination.datastore}</p>
      <p>Backup chain: {plan.jobIds.join(" → ")} · Required media: {plan.requiredMedia.join(", ")}</p>
      <p>Power: Off · Network: Disconnected · Overwrite: Never</p>
      <ul>{plan.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
      <p>{plan.dispatchEnabled ? "Destination verified. Confirm to create the new VM and restore its disks." : "Review only. No VM has been created or restored."}</p>
      <button className="button" ref={submit} disabled={!plan.dispatchEnabled} onClick={()=>{setSendError("");confirm.current?.showModal();back.current?.focus();}}>Restore new VMware VM</button>
    </div></div>}
    <dialog ref={confirm} className="restore-confirm" aria-labelledby="vm-restore-confirm-title" onCancel={e=>{if(lock.current)e.preventDefault();}} onClose={()=>submit.current?.focus()}>
      <div className="account-confirm"><h2 id="vm-restore-confirm-title">Create and restore {plan?.destination.vm_name}?</h2>
      <p>Restore backup chain {plan?.jobIds.join(" → ")} to {plan?.destination.host} / {plan?.destination.datastore}. Existing VMs will not be overwritten. The new VM has no network adapters and remains powered off.</p>
      <div className="dialog-actions"><button className="button" ref={back} disabled={sending} onClick={()=>confirm.current?.close()}>Go back</button>
      <button className="button" disabled={sending||!plan?.dispatchEnabled} onClick={async()=>{
        if(lock.current||!plan)return;lock.current=true;setSending(true);setSendError("");
        try { const r=await apiFetch("/api/recovery/vmware/restore",{method:"POST",headers:actionHeaders,body:JSON.stringify({source_job_id:jobId,destination:{...plan.destination,power:"off",network:"disconnected",overwrite:"Never"},review_digest:plan.reviewDigest,idempotency_key:key.current,confirmed:true})});const x=await r.json();if(!r.ok)throw new Error(typeof x.detail==="string"?x.detail:"Restore could not be queued. Check the operation journal before retrying.");confirm.current?.close();onDirty(false);onQueued(x); }
        catch(e){setSendError(e instanceof Error?e.message:"Delivery outcome unknown; check operation journal. Reuse this request when reconciling.");}
        finally{lock.current=false;setSending(false);}
      }}>{sending?"Queuing restore…":"Create and restore VM"}</button></div>
      {sendError&&<p role="alert">{sendError}</p>}</div>
    </dialog>
  </section>;
}
