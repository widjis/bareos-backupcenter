"use client";
import { useEffect, useRef, useState } from "react";
import { NativeDateField } from "./form-controls";
import { apiFetch } from "@/lib/api";
import { DataTable } from "./table-controls";
type Report = {
  scope: { name: string; connectionId: string };
  generatedAt: string;
  dateFrom: string;
  dateTo: string;
  total: number;
  limit: number;
  truncated: boolean;
  firstObservation: string | null;
  lastObservation: string | null;
  coverage: string;
  sessions: {
    id: number;
    name: string;
    status: string;
    level: string;
    started: string | null;
    bytes: number;
  }[];
};
const day = (d: Date) => {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Makassar",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const value = (type: string) => parts.find((p) => p.type === type)!.value;
  return value("year") + "-" + value("month") + "-" + value("day");
};
const reportTime = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Makassar",
      }).format(new Date(value)) + " WITA"
    : "Unknown";
export function SessionReport() {
  const [from, setFrom] = useState(() =>
      day(new Date(Date.now() - 29 * 86400000)),
    ),
    [to, setTo] = useState(() => day(new Date()));
  const [report, setReport] = useState<Report | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [page, setPage] = useState(1);
  const start = useRef<HTMLInputElement>(null),
    controller = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      controller.current?.abort();
      document.body.classList.remove("printing-report");
    },
    [],
  );
  const [attempted, setAttempted] = useState(false);
  const invalid =
    !from ||
    !to ||
    from > to ||
    (new Date(to).getTime() - new Date(from).getTime()) / 86400000 > 365;
  const params = new URLSearchParams({ date_from: from, date_to: to });
  return (
    <section className="panel session-report">
      <h2>Backup session report</h2>
      <p>
        Filter persisted observations by backup start date in WITA. This is an
        observed-history report, not a complete Catalog or recovery guarantee.
      </p>
      <form
        noValidate
        className="report-controls"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setAttempted(true);
          if (
            !from ||
            !to ||
            from > to ||
            (new Date(to).getTime() - new Date(from).getTime()) / 86400000 > 365
          ) {
            setError("Choose a valid period of at most 366 days.");
            start.current?.focus();
            return;
          }
          controller.current?.abort();
          controller.current = new AbortController();
          setBusy(true);
          setError("");
          try {
            const r = await apiFetch("/api/reports/backup-sessions?" + params, {
              signal: controller.current.signal,
            });
            const x = await r.json();
            if (!r.ok)
              throw new Error(
                typeof x.detail === "string" ? x.detail : "Report unavailable.",
              );
            setReport(x);
            setPage(1);
          } catch (e) {
            setError(e instanceof Error ? e.message : "Report unavailable.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <NativeDateField
          label="From date (WITA)"
          value={from}
          disabled={busy}
          invalid={attempted && invalid}
          describedBy="report-error"
          inputRef={start}
          onChange={(v) => {
            setFrom(v);
            setReport(null);
          }}
        />
        <NativeDateField
          label="Through date (WITA)"
          value={to}
          disabled={busy}
          invalid={attempted && invalid}
          describedBy="report-error"
          onChange={(v) => {
            setTo(v);
            setReport(null);
          }}
        />
        <button className="button" disabled={busy}>
          {busy ? "Loading…" : "Load report"}
        </button>
      </form>
      <p className="auth-error" id="report-error" role="alert">
        {error}
      </p>
      {report && (
        <>
          <div className="section-heading">
            <p>
              {report.scope.name} · {report.total} observed backup sessions ·{" "}
              {report.dateFrom} through {report.dateTo} · Asia/Makassar
            </p>
            <button
              className="button"
              onClick={() => {
                document.body.classList.add("printing-report");
                window.addEventListener(
                  "afterprint",
                  () => document.body.classList.remove("printing-report"),
                  { once: true },
                );
                window.print();
              }}
            >
              Print report page
            </button>
            <a
              className="button"
              href={"/api/reports/backup-sessions?" + params + "&format=csv"}
            >
              Export CSV
            </a>
          </div>
          <DataTable
            headers={[
              "Backup job",
              "JobId",
              "Level",
              "Last observed result",
              "Started WITA",
              "Recorded bytes",
            ]}
            rows={report.sessions.map((s) => [
              s.name,
              s.id,
              s.level,
              s.status,
              s.started
                ? new Intl.DateTimeFormat("en-GB", {
                    dateStyle: "medium",
                    timeStyle: "short",
                    timeZone: "Asia/Makassar",
                  }).format(new Date(s.started))
                : "Unknown",
              s.bytes.toLocaleString("en-GB"),
            ])}
            page={page}
            setPage={setPage}
            empty="No observed backups in this period"
          />
          <p>{report.coverage}</p>
          <small>
            Generated: {reportTime(report.generatedAt)} · Observation coverage
            began: {reportTime(report.firstObservation)} · Last observation:{" "}
            {reportTime(report.lastObservation)}
            {report.truncated ? " · Limited to first 5,000 records" : ""}
          </small>
        </>
      )}
    </section>
  );
}
