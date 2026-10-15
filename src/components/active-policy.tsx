"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders } from "./auth";
import { NativeDateField, NativeSelectField } from "./form-controls";
import { useUnsavedDraft } from "./draft-guard";
type Row = {
  job: string;
  timeWita: string;
  automatic: boolean;
  retentionDays: number;
  maximumVolumes: number;
};
type Definition = {
  jobs: string[];
  time_wita: string;
  retention_days: number;
  maximum_volumes: number;
  automatic: boolean;
};
type Plan = {
  definition: Definition;
  reviewDigest: string;
  existingVolumePolicy: string;
  doesNotRun: string;
};
type CurrentPolicy = {
  time: string;
  days: string;
  volumes: string;
  automatic: boolean;
  mixed: boolean;
};

function deriveCurrent(rows: Row[]): CurrentPolicy {
  const first = rows[0];
  if (!first) {
    return {
      time: "21:30",
      days: "30",
      volumes: "6",
      automatic: true,
      mixed: false,
    };
  }
  const mixed = rows.some(
    (row) =>
      row.timeWita !== first.timeWita ||
      row.automatic !== first.automatic ||
      row.retentionDays !== first.retentionDays ||
      row.maximumVolumes !== first.maximumVolumes,
  );
  return {
    time: first.timeWita,
    days: String(first.retentionDays),
    volumes: String(first.maximumVolumes),
    automatic: first.automatic,
    mixed,
  };
}

export function ActivePolicySettings() {
  const [invalid, setInvalid] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [jobs, setJobs] = useState<string[]>([]);
  const [time, setTime] = useState("21:30");
  const [days, setDays] = useState("30");
  const [volumes, setVolumes] = useState("6");
  const [automatic, setAutomatic] = useState(true);
  const [current, setCurrent] = useState<CurrentPolicy>(() =>
    deriveCurrent([]),
  );
  const [plan, setPlan] = useState<Plan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [attempted, setAttempted] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const key = useRef("");
  const lock = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const start = useRef<HTMLButtonElement>(null);
  const baseline = useRef(
    JSON.stringify({
      jobs: [],
      time: "21:30",
      days: "30",
      volumes: "6",
      automatic: true,
    }),
  );
  const draft = JSON.stringify({ jobs, time, days, volumes, automatic });
  const dirty = draft !== baseline.current;
  useUnsavedDraft(dirty);

  function applyCurrent(next: CurrentPolicy) {
    setTime(next.time);
    setDays(next.days);
    setVolumes(next.volumes);
    setAutomatic(next.automatic);
    setJobs([]);
    setPlan(null);
    setAttempted(false);
    setInvalid([]);
    baseline.current = JSON.stringify({
      jobs: [],
      time: next.time,
      days: next.days,
      volumes: next.volumes,
      automatic: next.automatic,
    });
  }

  async function load(forceDraftReset = false) {
    const r = await apiFetch("/api/policies/active", { cache: "no-store" });
    const x = await r.json();
    if (!r.ok) throw new Error(x.detail || "Active policy unavailable.");
    const nextRows = Array.isArray(x.jobs) ? x.jobs : [];
    const nextCurrent = deriveCurrent(nextRows);
    setRows(nextRows);
    setEnabled(Boolean(x.applyEnabled));
    setCurrent(nextCurrent);
    if (forceDraftReset || !dirty) applyCurrent(nextCurrent);
  }

  useEffect(() => {
    let stopped = false;
    apiFetch("/api/policies/active", { cache: "no-store" })
      .then(async (r) => {
        const x = await r.json();
        if (!r.ok) throw new Error(x.detail || "Active policy unavailable.");
        if (stopped) return;
        const nextRows = Array.isArray(x.jobs) ? x.jobs : [];
        const nextCurrent = deriveCurrent(nextRows);
        setRows(nextRows);
        setEnabled(Boolean(x.applyEnabled));
        setCurrent(nextCurrent);
        applyCurrent(nextCurrent);
      })
      .catch((e) => {
        if (!stopped) setError(e.message);
      });
    return () => {
      stopped = true;
    };
  }, []);

  function edit() {
    setInvalid([]);
    setPlan(null);
    setError("");
    setFeedback("");
  }

  async function status() {
    setBusy(true);
    setError("");
    try {
      const r = await apiFetch("/api/policies/active/status/" + key.current);
      const x = await r.json();
      if (!r.ok) throw new Error(x.detail);
      setFeedback("Application status: " + x.state);
      if (x.state === "Applied") {
        await load(true);
      } else if (x.state === "Failed") {
        setAttempted(false);
        setError(
          x.message || "Policy application failed; inspect the receipt.",
        );
      } else if (x.state === "Unknown") {
        setError(
          x.message ||
            "Policy outcome unknown; reconcile the server receipt before another request.",
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Status unavailable.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="panel policy-form active-policy-settings"
      aria-labelledby="active-policy-title"
    >
      <h3 id="active-policy-title">Active backup schedule and retention</h3>
      <p>
        Full on the 1st and 15th; Incremental on other days. Existing priorities
        and serial execution are preserved. Times use WITA (UTC+08).
      </p>
      <ul>
        {rows.map((row) => (
          <li key={row.job}>
            {row.job} · {row.automatic ? row.timeWita + " WITA" : "Manual"} ·{" "}
            {row.retentionDays} days · {row.maximumVolumes} volumes
          </li>
        ))}
      </ul>
      {rows.length > 0 && (
        <p>
          Current dashboard baseline:{" "}
          {current.automatic ? current.time + " WITA" : "Manual only"} ·{" "}
          {current.days} days · {current.volumes} volumes
          {current.mixed
            ? ". Managed jobs do not currently share one exact schedule/retention baseline; review the selected subset before applying."
            : "."}
        </p>
      )}
      {!rows.length && (
        <button
          className="button"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError("");
            load(true)
              .catch((e) => setError(e.message))
              .finally(() => setBusy(false));
          }}
        >
          Reload active policy
        </button>
      )}
      <form
        ref={form}
        noValidate
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy || lock.current) return;
          setError("");
          setPlan(null);
          if (!jobs.length) {
            setInvalid(["jobs"]);
            setError("Select at least one job.");
            form.current
              ?.querySelector<HTMLInputElement>('input[type="checkbox"]')
              ?.focus();
            return;
          }
          if (
            !Number.isInteger(Number(days)) ||
            !Number.isInteger(Number(volumes))
          ) {
            setError("Retention and volume limit must be whole numbers.");
            return;
          }
          setBusy(true);
          try {
            const r = await apiFetch("/api/policies/active/preview", {
              method: "POST",
              headers: actionHeaders,
              body: JSON.stringify({
                definition: {
                  jobs,
                  time_wita: time,
                  retention_days: Number(days),
                  maximum_volumes: Number(volumes),
                  automatic,
                },
              }),
            });
            const x = await r.json();
            if (!r.ok) {
              if (Array.isArray(x.detail)) {
                const bad = x.detail
                  .map((d: { loc?: string[] }) => d.loc?.at(-1))
                  .filter(Boolean);
                setInvalid(bad);
                const label = {
                  time_wita: "Backup start (WITA)",
                  automatic: "Automatic schedule",
                } as Record<string, string>;
                form.current
                  ?.querySelector<HTMLElement>(
                    label[bad[0]]
                      ? '[aria-label="' + label[bad[0]] + '"]'
                      : '[name="' + bad[0] + '"]',
                  )
                  ?.focus();
              }
              throw new Error(
                typeof x.detail === "string"
                  ? x.detail
                  : "Use a time after 21:00, retention of at least 30 days and enough volumes for retained chains.",
              );
            }
            setPlan(x);
            key.current = crypto.randomUUID();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Policy review failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset
          disabled={busy || attempted}
          aria-invalid={invalid.includes("jobs")}
          aria-describedby={
            invalid.includes("jobs") ? "active-policy-error" : undefined
          }
        >
          <legend>Jobs to change</legend>
          {rows.map((row) => (
            <label key={row.job} className="policy-job-choice">
              <input
                type="checkbox"
                checked={jobs.includes(row.job)}
                onChange={(e) => {
                  edit();
                  setJobs((currentJobs) =>
                    e.target.checked
                      ? [...currentJobs, row.job]
                      : currentJobs.filter((job) => job !== row.job),
                  );
                }}
              />
              {row.job}
            </label>
          ))}
        </fieldset>
        <div className="policy-fields">
          <NativeDateField
            kind="time"
            label="Backup start (WITA)"
            invalid={invalid.includes("time_wita")}
            describedBy={
              invalid.includes("time_wita") ? "active-policy-error" : undefined
            }
            value={time}
            disabled={busy || attempted}
            onChange={(value) => {
              edit();
              setTime(value);
            }}
          />
          <NativeSelectField
            label="Automatic schedule"
            value={automatic ? "yes" : "no"}
            disabled={busy || attempted}
            options={[
              {
                value: "yes",
                label: "Twice-monthly Full + daily Incremental",
              },
              { value: "no", label: "Manual only" },
            ]}
            onChange={(value) => {
              edit();
              setAutomatic(value === "yes");
            }}
          />
          <label className="auth-field">
            <span>Retention for new volumes (days)</span>
            <input
              name="retention_days"
              aria-invalid={invalid.includes("retention_days")}
              aria-describedby={
                invalid.includes("retention_days")
                  ? "active-policy-error"
                  : undefined
              }
              type="number"
              min={30}
              max={3650}
              value={days}
              disabled={busy || attempted}
              onChange={(e) => {
                edit();
                setDays(e.target.value);
              }}
            />
          </label>
          <label className="auth-field">
            <span>Maximum volumes per VM</span>
            <input
              name="maximum_volumes"
              aria-invalid={invalid.includes("maximum_volumes")}
              aria-describedby={
                invalid.includes("maximum_volumes")
                  ? "active-policy-error"
                  : undefined
              }
              type="number"
              min={6}
              max={1000}
              value={volumes}
              disabled={busy || attempted}
              onChange={(e) => {
                edit();
                setVolumes(e.target.value);
              }}
            />
          </label>
        </div>
        <p>
          Existing volumes retain their own minimum. Complete-chain cleanup uses
          the longer Pool/Volume retention and preserves the latest successful
          Full.
        </p>
        <div className="dialog-actions">
          <button
            className="button"
            disabled={busy || attempted || !rows.length}
          >
            Review active policy
          </button>
          <button
            className="button"
            type="button"
            disabled={busy || attempted || !rows.length || !dirty}
            onClick={() => {
              setError("");
              setFeedback("");
              applyCurrent(current);
            }}
          >
            Reset to current
          </button>
        </div>
      </form>
      {error && (
        <p id="active-policy-error" role="alert">
          {error}
        </p>
      )}
      {feedback && <p role="status">{feedback}</p>}
      {plan && (
        <div className="info-note">
          <div>
            <h4>Reviewed policy</h4>
            <p>{plan.definition.jobs.join(", ")}</p>
            <p>
              {plan.definition.automatic
                ? "Automatic at " + plan.definition.time_wita + " WITA"
                : "Manual only"}{" "}
              · Full 1/15 · {plan.definition.retention_days} days ·{" "}
              {plan.definition.maximum_volumes} volumes
            </p>
            <p>{plan.existingVolumePolicy}</p>
            <p>{plan.doesNotRun}</p>
            <button
              ref={start}
              className="button"
              disabled={!enabled || busy || attempted}
              onClick={() => {
                dialog.current?.showModal();
                back.current?.focus();
              }}
            >
              Apply reviewed policy
            </button>
            {!enabled && <p>Policy application is disabled by the server.</p>}
          </div>
        </div>
      )}
      {attempted && (
        <div>
          <p className="mono">Application request: {key.current}</p>
          <button className="button" disabled={busy} onClick={status}>
            Check application status
          </button>
        </div>
      )}
      <dialog
        ref={dialog}
        className="restore-confirm"
        aria-labelledby="active-policy-confirm"
        onCancel={(e) => {
          if (lock.current) e.preventDefault();
        }}
        onClose={() => start.current?.focus()}
      >
        <div className="account-confirm">
          <h2 id="active-policy-confirm">Apply schedule and retention?</h2>
          <p>
            Update only {plan?.definition.jobs.join(", ")}. The Director will
            validate and reload. Future retention runs use the reviewed minimum;
            this action does not run backups or cleanup.
          </p>
          <div className="dialog-actions">
            <button
              ref={back}
              className="button"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Go back
            </button>
            <button
              className="button"
              disabled={busy || attempted}
              onClick={async () => {
                if (lock.current || !plan) return;
                lock.current = true;
                setAttempted(true);
                setBusy(true);
                setError("");
                try {
                  const r = await apiFetch("/api/policies/active/apply", {
                    method: "POST",
                    headers: actionHeaders,
                    body: JSON.stringify({
                      definition: plan.definition,
                      request_id: key.current,
                      review_digest: plan.reviewDigest,
                      confirmed: true,
                    }),
                  });
                  const x = await r.json();
                  if (!r.ok) {
                    if (r.status >= 400 && r.status < 500) setAttempted(false);
                    throw new Error(
                      typeof x.detail === "string"
                        ? x.detail
                        : "Policy outcome unknown; check status.",
                    );
                  }
                  setFeedback("Application status: " + x.state);
                  if (x.state === "Applied") {
                    await load(true);
                  } else if (x.state === "Failed") {
                    setAttempted(false);
                    setError(
                      x.message ||
                        "Policy application failed; inspect the receipt.",
                    );
                  } else if (x.state === "Unknown") {
                    setError(
                      x.message ||
                        "Policy outcome unknown; reconcile the server receipt before another request.",
                    );
                  }
                  dialog.current?.close();
                } catch (e) {
                  setError(
                    e instanceof Error
                      ? e.message
                      : "Outcome unknown. Check application status.",
                  );
                  dialog.current?.close();
                } finally {
                  lock.current = false;
                  setBusy(false);
                }
              }}
            >
              {busy ? "Applying…" : "Apply policy"}
            </button>
          </div>
        </div>
      </dialog>
    </section>
  );
}
