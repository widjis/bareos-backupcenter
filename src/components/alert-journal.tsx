"use client";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders, useIdentity } from "./auth";
import { DataTable } from "./table-controls";
import { NativeSelectField } from "./form-controls";
type Alert = {
  id: string;
  job_name: string;
  source_job_id: number;
  severity: string;
  state: string;
  revision: number;
  evidence: Record<string, unknown>;
  acknowledged_by: string | null;
  resolved_by_job_id: number | null;
};
type Journal = {
  alerts: Alert[];
  limit: number;
  evaluationState: string;
  syncedAt: string;
  scope: string;
};
export function AlertJournal({
  onReview,
}: {
  onReview: (session: Record<string, unknown>) => void;
}) {
  const identity = useIdentity();
  const [data, setData] = useState<Journal | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [pending, setPending] = useState<string | null>(null),
    [filter, setFilter] = useState("All"),
    [page, setPage] = useState(1),
    [feedback, setFeedback] = useState("");
  const request = useRef<AbortController | null>(null);
  const load = async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const r = await apiFetch("/api/alerts", { signal: controller.signal });
      if (!r.ok)
        throw new Error("Alert journal unavailable. Retry the connection.");
      const next = await r.json();
      if (!controller.signal.aborted) setData(next);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Alert journal unavailable.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };
  useEffect(() => {
    void load();
    return () => request.current?.abort();
  }, []);
  const rows = (data?.alerts || []).filter(
    (a) => filter === "All" || a.state === filter,
  );
  return (
    <section className="panel alert-journal">
      <div className="section-heading">
        <div>
          <h2>Observed backup alerts</h2>
          <p>
            Failure/warning evidence from the latest observed terminal backup
            sessions.
          </p>
        </div>
        <button className="button" disabled={busy} onClick={() => void load()}>
          Refresh alerts
        </button>
      </div>
      <div className="alert-toolbar">
        <NativeSelectField
          label="Alert state"
          value={filter}
          onChange={(value) => {
            setFilter(value);
            setPage(1);
          }}
          options={["All", "Open", "Acknowledged", "Resolved"].map((v) => ({
            value: v,
            label: v,
          }))}
        />
        <p role="status">
          {busy
            ? "Loading alert journal…"
            : data
              ? "Evaluation: " + (error ? "stale" : data.evaluationState)
              : ""}
        </p>
      </div>
      {error && (
        <p className="auth-error" role="alert">
          {error}
        </p>
      )}
      <p role="status">{feedback}</p>
      {data && (
        <DataTable
          headers={[
            "Backup job",
            "Session",
            "Severity",
            "Alert state",
            "Review",
            "Action",
          ]}
          rows={rows.map((a) => [
            a.job_name,
            a.source_job_id,
            a.severity,
            a.state,
            <div key="review">
              <button
                className="text-button"
                onClick={() => onReview(a.evidence)}
              >
                Review session {a.source_job_id}
              </button>
              <small>
                {a.acknowledged_by
                  ? "Acknowledged by " + a.acknowledged_by
                  : "Review pending"}
                {a.resolved_by_job_id
                  ? " · Later successful JobId " + a.resolved_by_job_id
                  : ""}
              </small>
            </div>,
            a.state === "Open" && identity?.role === "Admin" ? (
              <button
                className="button"
                disabled={!!pending}
                onClick={async () => {
                  if (pending) return;
                  setPending(a.id);
                  setError("");
                  setFeedback("");
                  try {
                    const r = await apiFetch("/api/alerts/" + a.id + "/ack", {
                      method: "POST",
                      headers: actionHeaders,
                      body: JSON.stringify({ revision: a.revision }),
                    });
                    const x = await r.json();
                    if (!r.ok)
                      throw new Error(
                        typeof x.detail === "string"
                          ? x.detail
                          : "Acknowledgement failed.",
                      );
                    setFeedback(
                      "Alert acknowledged. Backup/recovery state is unchanged.",
                    );
                    await load();
                  } catch (e) {
                    setError(
                      e instanceof Error
                        ? e.message
                        : "Acknowledgement failed.",
                    );
                  } finally {
                    setPending(null);
                  }
                }}
              >
                {pending === a.id ? "Saving…" : "Acknowledge"}
              </button>
            ) : a.state === "Open" ? (
              "Admin review required"
            ) : (
              "—"
            ),
          ])}
          page={page}
          setPage={setPage}
          empty={
            filter === "All"
              ? "No observed failure or warning alerts"
              : "No alerts in this state"
          }
        />
      )}
      {data && (
        <small>
          {data.scope} Latest source observation:{" "}
          {new Intl.DateTimeFormat("en-GB", {
            dateStyle: "medium",
            timeStyle: "short",
            timeZone: "Asia/Makassar",
          }).format(new Date(data.syncedAt))}{" "}
          WITA · Up to {data.limit} alerts. Acknowledgement records review; only
          a later observed successful backup resolves the alert.
        </small>
      )}
    </section>
  );
}
