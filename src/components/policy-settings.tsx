"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders, useIdentity } from "./auth";
import { useUnsavedDraft } from "./draft-guard";
import { NativeDateField, NativeSelectField } from "./form-controls";
import { DataTable } from "./table-controls";
type Definition = {
  storage: string;
  freshness_hours: number;
  retention_days: number;
  maximum_volumes: number;
  schedule: "Manual" | "Daily";
  time_wita: string;
};
type Policy = {
  id: string;
  name: string;
  owner: string;
  revision: number;
  state: string;
  definition: Definition;
};
type PolicyFields = {
  name: string;
  storage: string;
  freshness: string;
  retention: string;
  volumes: string;
  schedule: string;
  time: string;
};
export function PolicySettings({
  storages,
}: {
  storages: { name: string; mediaType: string; enabled: boolean }[];
}) {
  const identity = useIdentity();
  const eligible = storages.filter(
    (s) => s.enabled && s.mediaType === "SMBFile",
  );
  const blank = (): PolicyFields => ({
    name: "",
    storage: eligible[0]?.name || "",
    freshness: "",
    retention: "30",
    volumes: "6",
    schedule: "Manual",
    time: "21:30",
  });
  const [form, setForm] = useState<PolicyFields>(blank),
    [policies, setPolicies] = useState<Policy[]>([]),
    [editing, setEditing] = useState<Policy | null>(null),
    [page, setPage] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [feedback, setFeedback] = useState("");
  const baseline = useRef(JSON.stringify(form)),
    fields = useRef<
      Record<string, HTMLInputElement | HTMLSelectElement | null>
    >({}),
    submit = useRef(false);
  const dirty = JSON.stringify(form) !== baseline.current;
  useUnsavedDraft(dirty);
  const load = async () => {
    const r = await apiFetch("/api/policies");
    if (!r.ok) throw new Error("Policy list unavailable.");
    setPolicies((await r.json()).policies);
  };
  useEffect(() => {
    void load().catch((e) => setError(e.message));
  }, []);
  const change = (key: keyof PolicyFields, value: string) => {
    setForm((old) => ({ ...old, [key]: value }));
    setErrors((old) => ({ ...old, [key]: "" }));
    setFeedback("");
  };
  const reset = () => {
    const next = blank();
    baseline.current = JSON.stringify(next);
    setForm(next);
    setEditing(null);
    setErrors({});
    setError("");
  };
  const edit = (policy: Policy) => {
    if (dirty) {
      setError(
        "Save or reset the current draft before editing another policy.",
      );
      return;
    }
    const d = policy.definition;
    const next = {
      name: policy.name,
      storage: d.storage,
      freshness: String(d.freshness_hours),
      retention: String(d.retention_days),
      volumes: String(d.maximum_volumes),
      schedule: d.schedule,
      time: d.time_wita,
    };
    baseline.current = JSON.stringify(next);
    setEditing(policy);
    setForm(next);
    setErrors({});
    setFeedback("");
    fields.current.name?.focus();
  };
  const validate = () => {
    const found: Record<string, string> = {};
    if (!/^[A-Za-z0-9][A-Za-z0-9 ._-]{2,79}$/.test(form.name))
      found.name =
        "Use 3–80 letters, numbers, spaces, dot, hyphen or underscore.";
    if (!eligible.some((s) => s.name === form.storage))
      found.storage = "Select an available shared SMB storage.";
    for (const [key, min, max] of [
      ["freshness", 1, 720],
      ["retention", 1, 3650],
      ["volumes", 2, 1000],
    ] as const) {
      if (
        !/^\d+$/.test(form[key]) ||
        Number(form[key]) < min ||
        Number(form[key]) > max
      )
        found[key] = `Enter a whole number from ${min} to ${max}.`;
    }
    if (form.schedule === "Daily" && Number(form.freshness) < 24)
      found.freshness =
        "Daily schedules require a freshness target of at least 24 hours.";
    if (!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(form.time))
      found.time = "Choose a valid time in WITA.";
    setErrors(found);
    const first = Object.keys(found)[0];
    if (first) fields.current[first]?.focus();
    return !first;
  };
  const numberField = (
    key: "freshness" | "retention" | "volumes",
    label: string,
  ) => (
    <label className="auth-field">
      <span>{label}</span>
      <input
        ref={(node) => {
          fields.current[key] = node;
        }}
        type="number"
        step="1"
        value={form[key]}
        disabled={busy}
        onChange={(e) => change(key, e.target.value)}
        aria-invalid={!!errors[key]}
        aria-describedby={"policy-" + key + "-error"}
      />
      <small className="auth-error" id={"policy-" + key + "-error"}>
        {errors[key]}
      </small>
    </label>
  );
  return (
    <section className="panel policy-settings">
      <h2>Draft protection policies</h2>
      <p>
        Reusable proposals for explicitly selected VMs. Saving a draft changes
        application metadata only; it does not configure jobs, retention cleanup
        or schedules.
      </p>
      <DataTable
        headers={[
          "Policy",
          "Owner",
          "Revision",
          "State",
          "Freshness target",
          "Action",
        ]}
        rows={policies.map((p) => [
          p.name,
          p.owner,
          p.revision,
          p.state,
          p.definition.freshness_hours + " hours",
          identity?.role === "Admin" ? (
            <button
              className="text-button"
              onClick={() => edit(p)}
              disabled={busy}
            >
              Edit {p.name}
            </button>
          ) : (
            "Read only"
          ),
        ])}
        page={page}
        setPage={setPage}
        empty="No draft policies"
      />
      <small>
        Showing up to 100 policy definitions for this environment. Draft targets
        are not evaluated as active protection.
      </small>
      {identity?.role === "Admin" && (
        <form
          noValidate
          className="policy-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (submit.current || !validate()) return;
            submit.current = true;
            setBusy(true);
            setError("");
            setFeedback("");
            try {
              const r = await apiFetch("/api/policies", {
                method: "POST",
                headers: actionHeaders,
                body: JSON.stringify({
                  id: editing?.id || null,
                  expected_revision: editing?.revision || 0,
                  name: form.name,
                  storage: form.storage,
                  freshness_hours: Number(form.freshness),
                  retention_days: Number(form.retention),
                  maximum_volumes: Number(form.volumes),
                  schedule: form.schedule,
                  time_wita: form.time,
                }),
              });
              const result = await r.json();
              if (!r.ok)
                throw new Error(
                  typeof result.detail === "string"
                    ? result.detail
                    : "Policy save failed. Review current values.",
                );
              baseline.current = JSON.stringify(form);
              setEditing(result);
              await load();
              setFeedback(
                "Draft policy saved. No Bareos configuration changed.",
              );
            } catch (e) {
              setError(e instanceof Error ? e.message : "Policy save failed.");
            } finally {
              submit.current = false;
              setBusy(false);
            }
          }}
        >
          <h3>
            {editing
              ? "Edit " + editing.name + " · revision " + editing.revision
              : "Create draft policy"}
          </h3>
          <div className="policy-fields">
            <label className="auth-field">
              <span>Policy name</span>
              <input
                ref={(node) => {
                  fields.current.name = node;
                }}
                value={form.name}
                disabled={busy}
                onChange={(e) => change("name", e.target.value)}
                aria-invalid={!!errors.name}
                aria-describedby="policy-name-error"
              />
              <small className="auth-error" id="policy-name-error">
                {errors.name}
              </small>
            </label>
            <div>
              <NativeSelectField
                label="Policy storage"
                value={form.storage}
                disabled={busy}
                invalid={!!errors.storage}
                describedBy="policy-storage-error"
                inputRef={(node) => {
                  fields.current.storage = node;
                }}
                onChange={(value) => change("storage", value)}
                options={
                  eligible.length
                    ? eligible.map((s) => ({ value: s.name, label: s.name }))
                    : [{ value: "", label: "No available shared storage" }]
                }
              />
              <small className="auth-error" id="policy-storage-error">
                {errors.storage}
              </small>
            </div>
            {numberField("freshness", "Backup freshness target (hours)")}
            {numberField("retention", "Proposed volume retention (days)")}
            {numberField("volumes", "Maximum volumes")}
            <NativeSelectField
              label="Schedule proposal"
              value={form.schedule}
              disabled={busy}
              onChange={(value) => change("schedule", value)}
              options={[
                { value: "Manual", label: "Manual" },
                { value: "Daily", label: "Daily" },
              ]}
            />
            <NativeDateField
              label="Proposed daily time (WITA)"
              kind="time"
              value={form.time}
              disabled={busy}
              invalid={!!errors.time}
              describedBy="policy-time-error"
              inputRef={(node) => {
                fields.current.time = node;
              }}
              onChange={(value) => change("time", value)}
            />
            <small className="auth-error" id="policy-time-error">
              {errors.time}
            </small>
          </div>
          <p>
            Owner: {editing?.owner || identity.username}. Daily proposal uses
            Full on the 1st/15th and Incremental on other days; Director UTC
            rules and script mappings require separate provisioning validation.
          </p>
          <div className="dialog-actions">
            <button className="button" type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save draft policy"}
            </button>
            <button
              className="button"
              type="button"
              disabled={busy}
              onClick={reset}
            >
              Reset draft
            </button>
          </div>
          <p className="auth-error" role="alert">
            {error}
          </p>
          <p role="status">{feedback}</p>
        </form>
      )}
    </section>
  );
}
