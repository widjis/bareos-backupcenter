"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { NativeSelectField } from "./form-controls";
import { apiFetch } from "@/lib/api";
import { actionHeaders } from "./auth";
type Storage = { name: string; mediaType: string; enabled: boolean };
type Policy = {
  id: string;
  name: string;
  revision: number;
  state: string;
  definition: {
    storage: string;
    retention_days: number;
    maximum_volumes: number;
  };
};
type Preview = {
  mode?: "live" | "rehearsal";
  applyEnabled: boolean;
  changes: {
    inventoryId: string;
    name: string;
    job: string;
    fileset: string;
    pool: string;
    storage: string;
    configuration: string;
  }[];
  blockers: string[];
  sharedImpact: string;
  scriptReview: {
    required: boolean;
    baselineCount: number;
    message: string;
    additions: {
      inventoryId: string;
      name: string;
      instanceUuid: string;
      job: string;
      prepareAllowlist: { script: string; action: string; entry: string };
      retentionAllowlist: { script: string; action: string; entry: string };
    }[];
  };
  policy: {
    name: string;
    retentionDays: number;
    maximumVolumes: number;
    schedule: string;
  };
};
export function OnboardingPreview({
  ids,
  storages,
  onQueued,
  onClose,
}: {
  ids: string[] | null;
  storages: Storage[];
  onQueued: (operation: {
    id: string;
    idempotency_key: string;
    kind: "provision";
    target: string;
    state: string;
    job_id: number | null;
    parameters: {
      message?: string;
      summary?: string;
      simulationOnly?: boolean;
    };
    created_at: string;
    updated_at: string;
  }) => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null),
    closeButton = useRef<HTMLButtonElement>(null),
    opener = useRef<HTMLElement | null>(null);
  const eligible = storages.filter(
    (s) => s.mediaType === "SMBFile" && s.enabled,
  );
  const [storage, setStorage] = useState(eligible[0]?.name || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [data, setData] = useState<Preview | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]),
    [policyId, setPolicyId] = useState("");
  const selectedPolicy = policies.find((p) => p.id === policyId);
  const abort = useRef<AbortController | null>(null);
  const applyKey = useRef<string | null>(null);
  useEffect(() => {
    if (!ids) return;
    setData(null);
    applyKey.current = null;
    setPolicyId("");
    void apiFetch("/api/policies")
      .then(async (r) => {
        if (r.ok) setPolicies((await r.json()).policies);
      })
      .catch(() => {});
    setError("");
    setStorage(eligible[0]?.name || "");
    opener.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
    closeButton.current?.focus();
    return () => {
      abort.current?.abort();
      dialog.current?.close();
      opener.current?.focus();
    };
  }, [ids]);
  return (
    <dialog
      ref={dialog}
      className="recovery-dialog"
      aria-labelledby="onboarding-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <div className="recovery-content">
        <div className="section-heading">
          <div>
            <h2 id="onboarding-title">Onboarding preview</h2>
            <p>{ids?.length || 0} explicitly selected VM(s)</p>
          </div>
          <button
            className="icon-button"
            ref={closeButton}
            disabled={busy}
            onClick={onClose}
            aria-label="Close onboarding preview"
          >
            <X size={18} />
          </button>
        </div>
        <div className="info-note">
          <span>
            This preview creates no jobs or schedules. Review the proposed
            resources before choosing a live Apply or a clearly marked
            rehearsal.
          </span>
        </div>
        <h3>Repository and baseline</h3>
        <form
          noValidate
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy || !ids) return;
            if (!storage) {
              setError("No eligible shared SMB storage is available.");
              return;
            }
            setBusy(true);
            setError("");
            abort.current = new AbortController();
            try {
              const r = await apiFetch("/api/provisioning/preview", {
                method: "POST",
                headers: actionHeaders,
                signal: abort.current.signal,
                body: JSON.stringify({
                  vm_ids: ids,
                  storage,
                  policy_id: policyId || null,
                  policy_revision:
                    policies.find((p) => p.id === policyId)?.revision || 0,
                }),
              });
              const x = await r.json();
              if (!r.ok)
                throw new Error(
                  typeof x.detail === "string"
                    ? x.detail
                    : "Preview validation failed.",
                );
              applyKey.current = null;
              setData(x);
            } catch (e) {
              if (!abort.current.signal.aborted)
                setError(e instanceof Error ? e.message : "Preview failed.");
            } finally {
              if (!abort.current.signal.aborted) setBusy(false);
            }
          }}
        >
          <NativeSelectField
            label="Draft policy"
            value={policyId}
            disabled={busy}
            onChange={(value) => {
              setPolicyId(value);
              const p = policies.find((p) => p.id === value);
              if (p) setStorage(p.definition.storage);
              setData(null);
            }}
            options={[
              { value: "", label: "Existing-environment baseline (proposal)" },
              ...policies
                .filter((p) => p.state === "Draft")
                .map((p) => ({
                  value: p.id,
                  label: p.name + " · revision " + p.revision,
                })),
            ]}
          />
          <NativeSelectField
            label="Existing shared storage"
            value={storage}
            disabled={busy || !!policyId}
            onChange={(v) => {
              setStorage(v);
              setData(null);
            }}
            options={
              eligible.length
                ? eligible.map((s) => ({ value: s.name, label: s.name }))
                : [{ value: "", label: "No eligible storage" }]
            }
          />
          <p>
            Proposed retention:{" "}
            {selectedPolicy?.definition.retention_days || 30} days · Maximum
            volumes: {selectedPolicy?.definition.maximum_volumes || 6} ·
            Schedule:{" "}
            {data?.mode === "live"
              ? "Full 1/15; Incremental other days; 21:30 UTC+8"
              : "disabled until reviewed"}
          </p>
          <button className="button" disabled={busy || !storage}>
            {busy ? "Generating…" : "Generate preview"}
          </button>
        </form>
        <p className="auth-error" role="alert">
          {error}
        </p>
        {data && (
          <>
            <h3>Configuration review</h3>
            <p>{data.sharedImpact}</p>
            {data.changes.map((c) => (
              <section
                className="panel configuration-preview"
                key={c.inventoryId}
              >
                <h4>{c.name}</h4>
                <p>
                  New job: {c.job} · Storage: {c.storage}
                </p>
                <pre>{c.configuration}</pre>
              </section>
            ))}
            <h3>Required before apply</h3>
            <ul>
              {data.blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
            <h3>Script mapping review</h3>
            <p>
              {data.scriptReview.message} Current baseline:{" "}
              {data.scriptReview.baselineCount} existing workload
              {data.scriptReview.baselineCount === 1 ? "" : "s"}.
            </p>
            {data.scriptReview.additions.length > 0 && (
              <div className="panel configuration-preview">
                {data.scriptReview.additions.map((item) => (
                  <div key={item.inventoryId}>
                    <h4>{item.name}</h4>
                    <p>
                      Generated job: {item.job}
                      <br />
                      Prepare allowlist: {item.prepareAllowlist.entry}
                      <br />
                      Retention allowlist: {item.retentionAllowlist.entry}
                    </p>
                  </div>
                ))}
              </div>
            )}
            <button
              className="button"
              disabled={busy || !data.applyEnabled}
              aria-describedby="apply-unavailable"
              onClick={async () => {
                if (busy || !ids) return;
                setBusy(true);
                setError("");
                abort.current = new AbortController();
                try {
                  const response = await apiFetch("/api/provisioning/apply", {
                    method: "POST",
                    headers: actionHeaders,
                    signal: abort.current.signal,
                    body: JSON.stringify({
                      vm_ids: ids,
                      storage,
                      policy_id: policyId || null,
                      policy_revision:
                        policies.find((p) => p.id === policyId)?.revision || 0,
                      idempotency_key: (applyKey.current ||=
                        crypto.randomUUID()),
                      confirmed: true,
                    }),
                  });
                  const payload = await response.json();
                  if (!response.ok)
                    throw new Error(
                      typeof payload.detail === "string"
                        ? payload.detail
                        : "Provisioning rehearsal failed.",
                    );
                  onQueued(payload);
                  onClose();
                } catch (e) {
                  if (!abort.current.signal.aborted)
                    setError(
                      e instanceof Error
                        ? e.message
                        : "Provisioning rehearsal failed.",
                    );
                } finally {
                  if (!abort.current.signal.aborted) setBusy(false);
                }
              }}
            >
              {busy
                ? "Queuing…"
                : data.mode === "live"
                  ? `Enable backup for ${data.changes[0]?.name}`
                  : "Stage dry-run apply"}
            </button>
            <p id="apply-unavailable">
              {data.mode === "live"
                ? "This applies the reviewed configuration for the approved test VM, creates its own repository folder and schedule, and preserves its power state. First backup remains a separate Run now action."
                : "This stages a durable rehearsal only. Generated local temporary fixtures are validated through the operation journal; existing Bareos resources remain unchanged and no Director reload occurs."}
            </p>
          </>
        )}
      </div>
    </dialog>
  );
}
