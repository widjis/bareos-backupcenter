"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders } from "./auth";
import { NativeDateField, NativeSelectField } from "./form-controls";
import { useUnsavedDraft } from "./draft-guard";
type Calendar = {
  mode: "daily" | "weekly" | "monthly" | "monthly_ordinal";
  weekdays: number[];
  monthdays: number[];
  full_mode: "monthdays" | "weekly" | "ordinal";
  full_days: number[];
  full_weekday: number;
  ordinal_week: number;
  ordinal_weekday: number;
  interval_hours?: number | null;
};
type AfterJob = {
  source_job: string;
  on_failure: "skip" | "run_anyway";
  level: "configured" | "full" | "incremental";
};
const defaultCalendar: Calendar = {
  mode: "daily",
  weekdays: [1, 2, 3, 4, 5, 6, 7],
  monthdays: Array.from({ length: 31 }, (_, i) => i + 1),
  full_mode: "monthdays",
  full_days: [1, 15],
  full_weekday: 7,
  ordinal_week: 4,
  ordinal_weekday: 6,
  interval_hours: null,
};
type Row = {
  calendar?: Calendar | null;
  job: string;
  timeWita: string;
  automatic: boolean;
  retentionDays: number;
  maximumVolumes: number;
  triggerMode?: "calendar" | "after_job";
  afterJob?: AfterJob | null;
  windowEndWita?: string | null;
  retryCount?: number;
  retryIntervalMinutes?: number;
};
type Definition = {
  jobs: string[];
  time_wita: string;
  retention_days: number;
  maximum_volumes: number;
  automatic: boolean;
  trigger_mode: "calendar" | "after_job";
  calendar?: Calendar | null;
  after_job?: AfterJob | null;
  window_end_wita?: string;
  retry_count: number;
  retry_interval_minutes: number;
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
const weekdayNames = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
const ordinalLabels = ["1st", "2nd", "3rd", "4th", "5th"];
const defaultAfterJob = (jobName = ""): AfterJob => ({
  source_job: jobName,
  on_failure: "skip",
  level: "configured",
});
function parseIntList(value: string) {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item));
}
function describePlan(plan: Definition) {
  const windowText = plan.window_end_wita
    ? `Window ${plan.time_wita}-${plan.window_end_wita} WITA`
    : plan.trigger_mode === "calendar"
      ? `Start ${plan.time_wita} WITA`
      : `Allowed after ${plan.time_wita} WITA`;
  const retryText = plan.retry_count
    ? `Retry ${plan.retry_count}x every ${plan.retry_interval_minutes} minutes`
    : "No automatic retry";
  if (plan.trigger_mode === "after_job" && plan.after_job) {
    const levelLabel =
      plan.after_job.level === "configured"
        ? "Configured default"
        : plan.after_job.level === "full"
          ? "Full"
          : "Incremental";
    return `${windowText} · After ${plan.after_job.source_job} · ${plan.after_job.on_failure === "run_anyway" ? "run even if the source fails" : "skip if the source fails"} · ${levelLabel} level · ${retryText}`;
  }
  if (!plan.calendar) {
    return `${windowText} · Full 1/15 · Incremental other days · ${retryText}`;
  }
  const intervalText = plan.calendar.interval_hours
    ? `every ${plan.calendar.interval_hours} hour${plan.calendar.interval_hours === 1 ? "" : "s"} within the window`
    : "once per selected day";
  if (plan.calendar.mode === "monthly_ordinal") {
    return `${windowText} · ${ordinalLabels[plan.calendar.ordinal_week - 1]} ${weekdayNames[plan.calendar.ordinal_weekday - 1]} · first run Full, later interval runs Incremental · ${intervalText} · ${retryText}`;
  }
  const runText =
    plan.calendar.mode === "weekly"
      ? `Run on ${plan.calendar.weekdays.map((day) => weekdayNames[day - 1]).join(", ")}`
      : plan.calendar.mode === "monthly"
        ? `Run on dates ${plan.calendar.monthdays.join(", ")}`
        : "Run every day";
  const fullText =
    plan.calendar.full_mode === "weekly"
      ? `Full every ${weekdayNames[plan.calendar.full_weekday - 1]}`
      : `Full on dates ${plan.calendar.full_days.join(", ")}`;
  return `${windowText} · ${runText} · ${fullText} · ${intervalText} · ${retryText}`;
}

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

export function ActivePolicySettings({ jobName }: { jobName?: string } = {}) {
  const [calendar, setCalendar] = useState<Calendar>(defaultCalendar);
  const currentRow = useRef<Row | null>(null);
  const [fullDates, setFullDates] = useState("1,15");
  const [runDates, setRunDates] = useState(defaultCalendar.monthdays.join(","));
  const [triggerMode, setTriggerMode] = useState<"calendar" | "after_job">(
    "calendar",
  );
  const [afterJob, setAfterJob] = useState<AfterJob>(defaultAfterJob());
  const [windowEnd, setWindowEnd] = useState("");
  const [retryCount, setRetryCount] = useState("0");
  const [retryInterval, setRetryInterval] = useState("30");
  const [invalid, setInvalid] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [dependencyJobs, setDependencyJobs] = useState<Row[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [applyBlocker, setApplyBlocker] = useState("");
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
  const draft = JSON.stringify({
    jobs,
    time,
    days,
    volumes,
    automatic,
    ...(jobName
      ? {
          triggerMode,
          calendar,
          afterJob,
          fullDates,
          runDates,
          windowEnd,
          retryCount,
          retryInterval,
        }
      : {}),
  });
  const dirty = draft !== baseline.current;
  useUnsavedDraft(dirty);

  function applyCurrent(next: CurrentPolicy, row = currentRow.current) {
    setTime(next.time);
    setDays(next.days);
    setVolumes(next.volumes);
    setAutomatic(next.automatic);
    setJobs(jobName ? [jobName] : []);
    const nextTriggerMode = row?.triggerMode || "calendar";
    const nextCalendar = row?.calendar || defaultCalendar;
    const nextAfterJob =
      row?.afterJob ||
      defaultAfterJob(dependencyJobs.find((item) => item.job !== jobName)?.job);
    setTriggerMode(nextTriggerMode);
    setCalendar(nextCalendar);
    setAfterJob(nextAfterJob);
    setFullDates(nextCalendar.full_days.join(","));
    setRunDates(nextCalendar.monthdays.join(","));
    setWindowEnd(row?.windowEndWita || "");
    setRetryCount(String(row?.retryCount || 0));
    setRetryInterval(String(row?.retryIntervalMinutes || 30));
    setPlan(null);
    setAttempted(false);
    setInvalid([]);
    baseline.current = JSON.stringify({
      jobs: jobName ? [jobName] : [],
      time: next.time,
      days: next.days,
      volumes: next.volumes,
      automatic: next.automatic,
      ...(jobName
        ? {
            triggerMode: nextTriggerMode,
            calendar: nextCalendar,
            afterJob: nextAfterJob,
            fullDates: nextCalendar.full_days.join(","),
            runDates: nextCalendar.monthdays.join(","),
            windowEnd: row?.windowEndWita || "",
            retryCount: String(row?.retryCount || 0),
            retryInterval: String(row?.retryIntervalMinutes || 30),
          }
        : {}),
    });
  }

  async function load(forceDraftReset = false) {
    const r = await apiFetch("/api/policies/active", { cache: "no-store" });
    const x = await r.json();
    if (!r.ok) throw new Error(x.detail || "Active policy unavailable.");
    setDependencyJobs(Array.isArray(x.jobs) ? x.jobs : []);
    const nextRows: Row[] = (Array.isArray(x.jobs) ? x.jobs : []).filter(
      (row: Row) => !jobName || row.job === jobName,
    );
    currentRow.current = nextRows[0] || null;
    const nextCurrent = deriveCurrent(nextRows);
    setRows(nextRows);
    setEnabled(Boolean(x.applyEnabled));
    setApplyBlocker(x.liveApplyBlocker || "");
    setCurrent(nextCurrent);
    if (forceDraftReset || !dirty)
      applyCurrent(nextCurrent, nextRows[0] || null);
  }

  useEffect(() => {
    let stopped = false;
    apiFetch("/api/policies/active", { cache: "no-store" })
      .then(async (r) => {
        const x = await r.json();
        if (!r.ok) throw new Error(x.detail || "Active policy unavailable.");
        if (stopped) return;
        setDependencyJobs(Array.isArray(x.jobs) ? x.jobs : []);
        const nextRows: Row[] = (Array.isArray(x.jobs) ? x.jobs : []).filter(
          (row: Row) => !jobName || row.job === jobName,
        );
        currentRow.current = nextRows[0] || null;
        const nextCurrent = deriveCurrent(nextRows);
        setRows(nextRows);
        setEnabled(Boolean(x.applyEnabled));
        setApplyBlocker(x.liveApplyBlocker || "");
        setCurrent(nextCurrent);
        applyCurrent(nextCurrent, nextRows[0] || null);
      })
      .catch((e) => {
        if (!stopped) setError(e.message);
      });
    return () => {
      stopped = true;
    };
  }, [jobName]);

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
      <h3 id="active-policy-title">
        {jobName
          ? "Schedule · " + jobName
          : "Active backup schedule and retention"}
      </h3>
      <p>
        Choose when this job runs, or have it follow another managed job.
        Existing priorities, storage ownership, and serial execution remain
        preserved. Times use WITA (UTC+08).
      </p>
      {jobName && (
        <p className="panel-footnote">
          This batch reuses the canonical schedule editor only. Job identity, VM
          assignment, repository ownership, and retirement changes remain
          unavailable here until their reviewed lifecycle contracts are ready.
        </p>
      )}
      <ul>
        {rows.map((row) => (
          <li key={row.job}>
            {row.job} ·{" "}
            {row.triggerMode === "after_job"
              ? `After ${row.afterJob?.source_job || "another managed job"}`
              : row.automatic
                ? row.timeWita + " WITA"
                : "Manual"}{" "}
            · {row.retentionDays} days · {row.maximumVolumes} volumes
            {row.calendar && !jobName && " · Custom calendar: edit from Jobs"}
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
                  trigger_mode: jobName ? triggerMode : "calendar",
                  retry_count: Number(retryCount),
                  retry_interval_minutes: Number(retryInterval),
                  ...(windowEnd ? { window_end_wita: windowEnd } : {}),
                  ...(jobName && triggerMode === "calendar"
                    ? {
                        calendar: {
                          ...calendar,
                          full_mode:
                            calendar.mode === "monthly_ordinal"
                              ? "ordinal"
                              : calendar.full_mode,
                          full_days:
                            calendar.full_mode === "monthdays"
                              ? parseIntList(fullDates)
                              : defaultCalendar.full_days,
                          monthdays:
                            calendar.mode === "monthly"
                              ? parseIntList(runDates)
                              : defaultCalendar.monthdays,
                        },
                      }
                    : {}),
                  ...(jobName && triggerMode === "after_job"
                    ? { after_job: afterJob }
                    : {}),
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
                  trigger_mode: "Start method",
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
                  : "Check schedule fields, a time after 21:00, any backup window, retention of at least 30 days, retry settings, and the required volume reserve.",
              );
            }
            setPlan(x);
            if (x.applyEnabled === false) {
              setEnabled(false);
              setApplyBlocker(
                x.liveApplyBlocker ||
                  "This review is local only; live Apply is unavailable.",
              );
            }
            key.current = crypto.randomUUID();
          } catch (e) {
            setError(e instanceof Error ? e.message : "Policy review failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        {!jobName && (
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
                  disabled={!!row.calendar}
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
        )}
        <div className="policy-fields">
          <NativeDateField
            kind="time"
            label={
              triggerMode === "after_job"
                ? "Backup window start (WITA)"
                : "Backup start (WITA)"
            }
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
            disabled={busy || attempted || triggerMode === "after_job"}
            options={[
              {
                value: "yes",
                label: "Enabled",
              },
              { value: "no", label: "Manual only" },
            ]}
            onChange={(value) => {
              edit();
              setAutomatic(value === "yes");
            }}
          />
          {jobName && (
            <>
              <NativeSelectField
                label="Start method"
                value={triggerMode}
                disabled={busy || attempted}
                options={[
                  { value: "calendar", label: "Calendar" },
                  { value: "after_job", label: "After another job" },
                ]}
                onChange={(value) => {
                  edit();
                  const next = value as "calendar" | "after_job";
                  setTriggerMode(next);
                  if (next === "calendar") {
                    setCalendar((currentCalendar) => ({
                      ...currentCalendar,
                      full_mode:
                        currentCalendar.full_mode === "ordinal"
                          ? "monthdays"
                          : currentCalendar.full_mode,
                    }));
                  } else {
                    setAutomatic(true);
                    setAfterJob(
                      afterJob.source_job
                        ? afterJob
                        : defaultAfterJob(
                            dependencyJobs.find((item) => item.job !== jobName)
                              ?.job,
                          ),
                    );
                  }
                }}
              />
              {triggerMode === "calendar" ? (
                <>
                  <NativeSelectField
                    label="Run schedule"
                    value={calendar.mode}
                    disabled={busy || attempted}
                    options={[
                      { value: "daily", label: "Every day" },
                      { value: "weekly", label: "Selected weekdays" },
                      { value: "monthly", label: "Selected dates each month" },
                      {
                        value: "monthly_ordinal",
                        label: "Monthly ordinal weekday",
                      },
                    ]}
                    onChange={(value) => {
                      edit();
                      setCalendar((currentCalendar) => ({
                        ...currentCalendar,
                        mode: value as Calendar["mode"],
                        full_mode:
                          value === "weekly"
                            ? "weekly"
                            : value === "monthly_ordinal"
                              ? "ordinal"
                              : currentCalendar.full_mode === "ordinal"
                                ? "monthdays"
                                : currentCalendar.full_mode,
                      }));
                    }}
                  />
                  <NativeSelectField
                    label="Run frequency"
                    value={
                      calendar.interval_hours
                        ? String(calendar.interval_hours)
                        : "once"
                    }
                    disabled={busy || attempted}
                    options={[
                      { value: "once", label: "Once per day" },
                      { value: "1", label: "Every 1 hour" },
                      { value: "2", label: "Every 2 hours" },
                      { value: "3", label: "Every 3 hours" },
                      { value: "4", label: "Every 4 hours" },
                      { value: "6", label: "Every 6 hours" },
                    ]}
                    onChange={(value) => {
                      edit();
                      setCalendar((currentCalendar) => ({
                        ...currentCalendar,
                        interval_hours: value === "once" ? null : Number(value),
                      }));
                    }}
                  />
                  {calendar.mode === "daily" && (
                    <NativeSelectField
                      label="Full backup schedule"
                      value={
                        calendar.full_mode === "ordinal"
                          ? "monthdays"
                          : calendar.full_mode
                      }
                      disabled={busy || attempted}
                      options={[
                        { value: "monthdays", label: "Dates each month" },
                        { value: "weekly", label: "Weekly" },
                      ]}
                      onChange={(value) => {
                        edit();
                        setCalendar((currentCalendar) => ({
                          ...currentCalendar,
                          full_mode: value as Calendar["full_mode"],
                        }));
                      }}
                    />
                  )}
                  {calendar.mode === "weekly" && (
                    <fieldset disabled={busy || attempted}>
                      <legend>Run on weekdays</legend>
                      {weekdayNames.map((name, i) => (
                        <label key={name} className="policy-job-choice">
                          <input
                            type="checkbox"
                            checked={calendar.weekdays.includes(i + 1)}
                            onChange={(e) => {
                              edit();
                              setCalendar((currentCalendar) => ({
                                ...currentCalendar,
                                weekdays: e.target.checked
                                  ? [...currentCalendar.weekdays, i + 1]
                                  : currentCalendar.weekdays.filter(
                                      (day) => day !== i + 1,
                                    ),
                              }));
                            }}
                          />
                          {name}
                        </label>
                      ))}
                    </fieldset>
                  )}
                  {calendar.mode === "monthly" && (
                    <label className="auth-field">
                      <span>Run dates (comma-separated)</span>
                      <input
                        value={runDates}
                        disabled={busy || attempted}
                        onChange={(e) => {
                          edit();
                          setRunDates(e.target.value);
                        }}
                      />
                      <small>Dates 29–31 are skipped in shorter months.</small>
                    </label>
                  )}
                  {calendar.mode === "monthly_ordinal" && (
                    <>
                      <NativeSelectField
                        label="Run on"
                        value={String(calendar.ordinal_week)}
                        disabled={busy || attempted}
                        options={ordinalLabels.map((label, index) => ({
                          value: String(index + 1),
                          label,
                        }))}
                        onChange={(value) => {
                          edit();
                          setCalendar((currentCalendar) => ({
                            ...currentCalendar,
                            ordinal_week: Number(value),
                            full_mode: "ordinal",
                          }));
                        }}
                      />
                      <NativeSelectField
                        label="Weekday"
                        value={String(calendar.ordinal_weekday)}
                        disabled={busy || attempted}
                        options={weekdayNames.map((name, index) => ({
                          value: String(index + 1),
                          label: name,
                        }))}
                        onChange={(value) => {
                          edit();
                          setCalendar((currentCalendar) => ({
                            ...currentCalendar,
                            ordinal_weekday: Number(value),
                            full_mode: "ordinal",
                          }));
                        }}
                      />
                    </>
                  )}
                  {calendar.full_mode === "weekly" ? (
                    <NativeSelectField
                      label="Full backup weekday"
                      value={String(calendar.full_weekday)}
                      disabled={busy || attempted}
                      options={weekdayNames.map((name, i) => ({
                        value: String(i + 1),
                        label: name,
                      }))}
                      onChange={(value) => {
                        edit();
                        setCalendar((currentCalendar) => ({
                          ...currentCalendar,
                          full_weekday: Number(value),
                        }));
                      }}
                    />
                  ) : calendar.mode !== "monthly_ordinal" ? (
                    <label className="auth-field">
                      <span>Full backup dates (comma-separated)</span>
                      <input
                        value={fullDates}
                        disabled={busy || attempted}
                        onChange={(e) => {
                          edit();
                          setFullDates(e.target.value);
                        }}
                      />
                      <small>
                        Other scheduled runs are Incremental. Include a Full
                        date between 1 and 28.
                      </small>
                    </label>
                  ) : (
                    <p className="auth-field">
                      <span>Full cadence</span>
                      <small>
                        The first run on the selected ordinal weekday is Full.
                        Additional interval runs that same day are Incremental.
                      </small>
                    </p>
                  )}
                </>
              ) : (
                <>
                  <NativeSelectField
                    label="After this job"
                    value={afterJob.source_job}
                    disabled={busy || attempted}
                    options={dependencyJobs
                      .filter((row) => row.job !== jobName)
                      .map((row) => ({ value: row.job, label: row.job }))}
                    onChange={(value) => {
                      edit();
                      setAfterJob((currentAfterJob) => ({
                        ...currentAfterJob,
                        source_job: value,
                      }));
                    }}
                  />
                  <NativeSelectField
                    label="If previous job fails"
                    value={afterJob.on_failure}
                    disabled={busy || attempted}
                    options={[
                      { value: "skip", label: "Skip this job" },
                      { value: "run_anyway", label: "Run anyway" },
                    ]}
                    onChange={(value) => {
                      edit();
                      setAfterJob((currentAfterJob) => ({
                        ...currentAfterJob,
                        on_failure: value as AfterJob["on_failure"],
                      }));
                    }}
                  />
                  <NativeSelectField
                    label="Triggered backup level"
                    value={afterJob.level}
                    disabled={busy || attempted}
                    options={[
                      { value: "configured", label: "Configured default" },
                      { value: "full", label: "Full" },
                      { value: "incremental", label: "Incremental" },
                    ]}
                    onChange={(value) => {
                      edit();
                      setAfterJob((currentAfterJob) => ({
                        ...currentAfterJob,
                        level: value as AfterJob["level"],
                      }));
                    }}
                  />
                </>
              )}
            </>
          )}
          {jobName && (
            <>
              <label className="auth-field">
                <span>Backup window end (WITA)</span>
                <input
                  type="time"
                  name="window_end_wita"
                  value={windowEnd}
                  disabled={busy || attempted}
                  onChange={(e) => {
                    edit();
                    setWindowEnd(e.target.value);
                  }}
                />
                <small>
                  Interval calendars require an end time. In after-job mode,
                  this limits when the dependency trigger may start a new run.
                </small>
              </label>
              <label className="auth-field">
                <span>Automatic retry count</span>
                <input
                  name="retry_count"
                  type="number"
                  min={0}
                  max={10}
                  value={retryCount}
                  disabled={busy || attempted}
                  onChange={(e) => {
                    edit();
                    setRetryCount(e.target.value);
                  }}
                />
              </label>
              <label className="auth-field">
                <span>Retry delay (minutes)</span>
                <input
                  name="retry_interval_minutes"
                  type="number"
                  min={5}
                  max={1440}
                  value={retryInterval}
                  disabled={busy || attempted}
                  onChange={(e) => {
                    edit();
                    setRetryInterval(e.target.value);
                  }}
                />
              </label>
            </>
          )}
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
            <p>{describePlan(plan.definition)}</p>
            <p>
              {plan.definition.automatic ? "Automatic" : "Manual only"} ·{" "}
              {plan.definition.retention_days} days ·{" "}
              {plan.definition.maximum_volumes} volumes
            </p>
            {plan.definition.calendar?.mode === "monthly" && (
              <p>Dates 29–31 are skipped in shorter months.</p>
            )}
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
            {!enabled && (
              <p>
                {applyBlocker ||
                  "Policy application is disabled by the server."}
              </p>
            )}
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
            validate and reload the reviewed scheduling, retry, and retention
            changes. This action does not run backups or cleanup.
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
