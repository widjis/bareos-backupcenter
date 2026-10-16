"use client";
import { useEffect, useId, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

type Preview = {
  jobName: string;
  executionSupported: false;
  blockers: { code: string; summary: string }[];
  impacts: { code: string; summary: string }[];
};

export function DisablePreview({ jobName }: { jobName: string }) {
  const [opened, setOpened] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const title = useId();
  useEffect(() => {
    if (!opened) return;
    dialog.current?.showModal();
    close.current?.focus();
    return () => {
      dialog.current?.close();
      trigger.current?.focus();
    };
  }, [opened]);
  useEffect(() => {
    if (!opened) return;
    const controller = new AbortController();
    let live = true;
    const timer = setTimeout(() => controller.abort(), 15000);
    setPreview(null);
    setError("");
    void (async () => {
      try {
        const response = await apiFetch("/api/jobs/disable/preview", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Backup-Center-Action": "confirmed",
          },
          body: JSON.stringify({ job_name: jobName }),
          signal: controller.signal,
        });
        if (!response.ok)
          throw new Error(
            "Review unavailable. Retry to fetch current evidence. No settings changed.",
          );
        const result = await response.json();
        if (
          result.jobName !== jobName ||
          result.executionSupported !== false ||
          !Array.isArray(result.blockers) ||
          !Array.isArray(result.impacts)
        )
          throw new Error(
            "Review response is incomplete. No settings changed.",
          );
        if (live) setPreview(result);
      } catch (cause) {
        if (live)
          setError(
            controller.signal.aborted
              ? "Review timed out. Retry to fetch current evidence. No settings changed."
              : cause instanceof Error
                ? cause.message
                : "Review unavailable. No settings changed.",
          );
      } finally {
        clearTimeout(timer);
      }
    })();
    return () => {
      live = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [opened, attempt, jobName]);
  return (
    <>
      <button
        ref={trigger}
        className="button compact"
        aria-label={`Review disable for ${jobName}`}
        onClick={() => setOpened(true)}
      >
        Review disable
      </button>
      <dialog
        ref={dialog}
        className="restore-confirm disable-review"
        aria-labelledby={title}
        onCancel={(event) => {
          event.preventDefault();
          setOpened(false);
        }}
      >
        <div className="account-confirm">
          <h2 id={title}>Review disable schedule</h2>
          <p className="mono">{jobName}</p>
          <p>
            This review does not change the schedule. Existing backups are
            preserved.
          </p>
          {!preview && !error && (
            <p role="status">Checking current job evidence…</p>
          )}
          {error && <p role="alert">{error}</p>}
          {preview && (
            <div role="status">
              <p>
                Disable is not available yet. Complete configuration and
                activity evidence is required.
              </p>
              {preview.blockers.length > 0 && (
                <>
                  <h3>What prevents disabling</h3>
                  <ul>
                    {preview.blockers.map((item, index) => (
                      <li key={`${item.code}-${index}`}>{item.summary}</li>
                    ))}
                  </ul>
                </>
              )}
              {preview.impacts.length > 0 && (
                <>
                  <h3>Expected impact</h3>
                  <ul>
                    {preview.impacts.map((item, index) => (
                      <li key={`${item.code}-${index}`}>{item.summary}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
          <div className="dialog-actions">
            <button
              ref={close}
              className="button"
              onClick={() => setOpened(false)}
            >
              Close
            </button>
            {(error || preview) && (
              <button
                className="button"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Refresh review
              </button>
            )}
          </div>
        </div>
      </dialog>
    </>
  );
}
