"use client";
import { useEffect,useState } from "react";
import { apiFetch } from "@/lib/api";
type Progress={warnings?:{kind:string;explanation:string;text:string}[];jobId:number;active:boolean;status:string;phase:string;elapsedSeconds:number|null;bytes:number;files:number;errors:number;observedAt:string;lines:{time:string;text:string}[]};
export function RestoreProgress({jobId}:{jobId:number}){
 const [data,setData]=useState<Progress|null>(null),[error,setError]=useState(""),[retry,setRetry]=useState(0);
 useEffect(()=>{let stopped=false,timer:ReturnType<typeof setTimeout>|undefined;const a=new AbortController();let loading=false,terminal=false;setData(null);setError("");
  async function poll(){if(stopped||loading||terminal)return;if(document.hidden){timer=setTimeout(poll,3000);return;}loading=true;
   try{const r=await apiFetch("/api/sessions/"+jobId+"/progress",{signal:a.signal,cache:"no-store"});const x=await r.json();if(!r.ok)throw new Error(typeof x.detail==="string"?x.detail:"Progress unavailable.");if(!stopped){setData(x);setError("");terminal=!x.active;}}
   catch(e){if(!stopped&&!a.signal.aborted)setError(e instanceof Error?e.message:"Progress unavailable.");}
   finally{loading=false;if(!stopped&&!terminal)timer=setTimeout(poll,3000);}
  }
  const visible=()=>{if(!document.hidden){clearTimeout(timer);void poll();}};document.addEventListener("visibilitychange",visible);void poll();return()=>{stopped=true;a.abort();clearTimeout(timer);document.removeEventListener("visibilitychange",visible);};
 },[jobId,retry]);
 const size=(n:number)=>(n/1024**3).toFixed(2)+" GiB";
 const elapsed=data?.elapsedSeconds;const duration=elapsed==null?"Unavailable":Math.floor(elapsed/60)+"m "+elapsed%60+"s";
 return <section className="panel restore-progress" aria-label={"Restore progress Job "+jobId}>
  <h3>Restore progress · Job #{jobId}</h3>
  {!data&&!error&&<p role="status">Connecting to Bareos progress…</p>}
  {error&&<div role="alert"><p>{error} {data?"Showing the last received values.":""}</p><button className="button" onClick={()=>setRetry(x=>x+1)}>Retry progress</button></div>}
  {data&&<><p role="status"><strong>{error?"Stale · ":""}{data.phase}</strong> · {data.status}</p>
   <p>Elapsed: {duration} · Catalog bytes: {size(data.bytes)} · Files: {data.files} · Errors: {data.errors}</p>
   <p>{data.active?"Updates every 3 seconds. Progress percentage is unavailable. Catalog counters may stay unchanged until completion.":"Session ended. Automatic polling stopped. These are final Catalog counters."}</p>
   <small>Last received: {new Date(data.observedAt).toLocaleString("en-GB",{timeZone:"Asia/Makassar"})} WITA</small>
   {!!data.warnings?.length && <section aria-label="Restore warning explanations"><h4>Why this restore has warnings</h4>
    {data.warnings.map((w,i)=><details key={i}><summary>{w.kind==="identity-change"?"Restored VM identity changed":"Warning needs review"}</summary><p>{w.explanation}</p><pre className="restore-warning-text">{w.text}</pre></details>)}
    <p>Warning classification does not verify VM boot or guest applications.</p>
   </section>}
   <details><summary>Latest restore log ({data.lines.length} lines)</summary><div className="log-view">{data.lines.map((l,i)=><div key={i}><time>{l.time}</time><pre>{l.text}</pre></div>)}{!data.lines.length&&<p>No restore log received yet.</p>}</div></details>
  </>}
 </section>;
}
