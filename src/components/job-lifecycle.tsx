"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { actionHeaders } from "./auth";

type LifecycleAction = "disable" | "enable" | "clone" | "remove";

type LifecycleReadiness = "blocked" | "review_only" | "candidate_ready";

type ReviewItem = {
  code: string;
  summary: string;
  severity?: "info" | "warning" | "obligation";
};

type ReviewResult = {
  action: string;
  blockers: ReviewItem[];
  duplicateProtection?: unknown;
  draftPlan?: unknown;
  executionSupported: boolean;
  impacts: ReviewItem[];
  jobName?: string;
  preserveBackupData?: boolean;
  proofRevision: number;
  readiness: LifecycleReadiness;
  resourceOwnership?: unknown;
  retainedObligations?: string[];
  retainedRecovery?: unknown;
  retirementRecord?: unknown;
  reviewDigest: string;
  summary: string;
  unsupportedChanges?: string[];
};

type OperationRecord = {
  id?: string;
  kind?: string;
  parameters?: { message?: string; summary?: string } & Record<string, unknown>;
  state?: string;
  target?: string;
};

const actionCopy: Record<
  LifecycleAction,
  {
    actionLabel: string;
    confirmLabel: string;
    description: string;
    reviewLabel: string;
    route: string;
    title: string;
  }
> = {
  disable: {
    actionLabel: "Disable",
    confirmLabel: "Disable schedule",
    description:
      "Stop automatic schedule delivery for this managed job. Existing backups stay available.",
    reviewLabel: "Review disable",
    route: "disable",
    title: "Review disable schedule",
  },
  enable: {
    actionLabel: "Enable",
    confirmLabel: "Enable schedule",
    description:
      "Restore the reviewed automatic schedule for this managed job. Existing backups stay available.",
    reviewLabel: "Review enable",
    route: "enable",
    title: "Review enable schedule",
  },
  clone: {
    actionLabel: "Clone",
    confirmLabel: "Create clone draft",
    description:
      "Create a disabled reviewed clone draft. Recovery history and secrets are not copied.",
    reviewLabel: "Review clone",
    route: "clone",
    title: "Review clone draft",
  },
  remove: {
    actionLabel: "Delete config",
    confirmLabel: "Delete configuration",
    description:
      "Remove the managed job configuration only. Backup data is kept and stays discoverable through retained recovery records.",
    reviewLabel: "Review delete",
    route: "remove",
    title: "Review configuration removal",
  },
};

function prettyState(value: LifecycleReadiness) {
  if (value === "candidate_ready") return "Candidate ready";
  if (value === "review_only") return "Review only";
  return "Blocked";
}

function normalizeReview(
  action: LifecycleAction,
  jobName: string,
  value: any,
): ReviewResult {
  const readiness = value?.readiness;
  const reviewDigest = value?.reviewDigest;
  const proofRevision = value?.proofRevision;
  const blockers = Array.isArray(value?.blockers) ? value.blockers : null;
  const impacts = Array.isArray(value?.impacts) ? value.impacts : null;
  if (
    !["blocked", "review_only", "candidate_ready"].includes(readiness) ||
    typeof reviewDigest !== "string" ||
    !/^[0-9a-f]{64}$/.test(reviewDigest) ||
    typeof proofRevision !== "number" ||
    !blockers ||
    !impacts ||
    typeof value?.executionSupported !== "boolean"
  ) {
    throw new Error(
      "Lifecycle review response is incomplete. No settings changed.",
    );
  }
  const normalized: ReviewResult = {
    action: String(value.action || action),
    blockers: blockers.map((item: any) => ({
      code: String(item?.code || "unknown"),
      summary: String(item?.summary || "Missing blocker summary."),
    })),
    duplicateProtection: value.duplicateProtection,
    draftPlan: value.draftPlan,
    executionSupported: value.executionSupported,
    impacts: impacts.map((item: any) => ({
      code: String(item?.code || "unknown"),
      severity:
        item?.severity === "warning" || item?.severity === "obligation"
          ? item.severity
          : "info",
      summary: String(item?.summary || "Missing impact summary."),
    })),
    jobName: String(value.jobName || jobName),
    preserveBackupData:
      typeof value.preserveBackupData === "boolean"
        ? value.preserveBackupData
        : undefined,
    proofRevision,
    readiness,
    resourceOwnership: value.resourceOwnership,
    retainedObligations: Array.isArray(value.retainedObligations)
      ? value.retainedObligations.map(String)
      : [],
    retainedRecovery: value.retainedRecovery,
    retirementRecord: value.retirementRecord,
    reviewDigest,
    summary:
      typeof value.summary === "string" && value.summary.trim()
        ? value.summary
        : actionCopy[action].description,
    unsupportedChanges: Array.isArray(value.unsupportedChanges)
      ? value.unsupportedChanges.map(String)
      : [],
  };
  return normalized;
}

function isOperationRecord(value: any): value is OperationRecord {
  return Boolean(
    value &&
    typeof value === "object" &&
    typeof value.id === "string" &&
    typeof value.state === "string",
  );
}

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function JobLifecycleAction({
  action,
  jobName,
  onApplied,
}: {
  action: LifecycleAction;
  jobName: string;
  onApplied?: () => void | Promise<void>;
}) {
  const copy = actionCopy[action];
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  const cloneInput = useRef<HTMLInputElement>(null);
  const reviewAbort = useRef<AbortController | null>(null);
  const title = useId();

  const [opened, setOpened] = useState(false);
  const [step, setStep] = useState<"form" | "review" | "confirm" | "result">(
    action === "clone" ? "form" : "review",
  );
  const [cloneName, setCloneName] = useState(`${jobName} Copy`);
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [error, setError] = useState("");
  const [operation, setOperation] = useState<OperationRecord | null>(null);
  const [requestKey, setRequestKey] = useState("");
  const [attempted, setAttempted] = useState(false);

  const canExecute = Boolean(
    review &&
    review.executionSupported &&
    review.readiness === "candidate_ready" &&
    !attempted,
  );
  const payload = useMemo(() => {
    if (action === "clone") {
      return {
        sourceJobName: jobName,
        newJobName: cloneName.trim(),
      };
    }
    return { jobName };
  }, [action, cloneName, jobName]);

  useEffect(() => {
    if (!opened) return;
    dialog.current?.showModal();
    if (step === "form") cloneInput.current?.focus();
    else primary.current?.focus();
    return () => {
      dialog.current?.close();
      trigger.current?.focus();
    };
  }, [opened, step]);

  async function fetchReview() {
    reviewAbort.current?.abort();
    const controller = new AbortController();
    reviewAbort.current = controller;
    const timer = setTimeout(() => controller.abort(), 15000);
    setReviewBusy(true);
    setError("");
    setReview(null);
    setOperation(null);
    setAttempted(false);
    try {
      if (action === "clone" && !cloneName.trim()) {
        throw new Error("Enter a unique clone job name before review.");
      }
      const response = await apiFetch(
        `/api/jobs/lifecycle/${copy.route}/review`,
        {
          method: "POST",
          headers: actionHeaders,
          body: JSON.stringify(payload),
          signal: controller.signal,
        },
      );
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Lifecycle review unavailable. No settings changed.",
        );
      }
      setReview(normalizeReview(action, jobName, result));
      setRequestKey(crypto.randomUUID());
      setStep("review");
    } catch (cause) {
      setError(
        controller.signal.aborted
          ? "Lifecycle review timed out. Retry to fetch current evidence. No settings changed."
          : cause instanceof Error
            ? cause.message
            : "Lifecycle review unavailable. No settings changed.",
      );
    } finally {
      clearTimeout(timer);
      if (reviewAbort.current === controller) reviewAbort.current = null;
      setReviewBusy(false);
    }
  }

  async function apply() {
    if (!review || !requestKey || applyBusy || attempted) return;
    setApplyBusy(true);
    setAttempted(true);
    setError("");
    try {
      const response = await apiFetch(`/api/jobs/lifecycle/${copy.route}`, {
        method: "POST",
        headers: actionHeaders,
        body: JSON.stringify({
          ...payload,
          reviewDigest: review.reviewDigest,
          proofRevision: review.proofRevision,
          idempotencyKey: requestKey,
          confirmed: true,
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status >= 400 && response.status < 500)
          setAttempted(false);
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Lifecycle outcome unknown. Check application status before sending another request.",
        );
      }
      if (!isOperationRecord(result)) {
        throw new Error(
          "Lifecycle apply response is incomplete. Check application status before sending another request.",
        );
      }
      setOperation(result);
      setStep("result");
      if (
        result.state === "Applied" ||
        result.state === "Completed" ||
        result.state === "Succeeded"
      ) {
        await onApplied?.();
      }
    } catch (cause) {
      setStep("result");
      setError(
        cause instanceof Error
          ? cause.message
          : "Lifecycle outcome unknown. Check application status before sending another request.",
      );
    } finally {
      setApplyBusy(false);
    }
  }

  async function checkStatus() {
    if (!operation?.id || statusBusy) return;
    setStatusBusy(true);
    setError("");
    try {
      const response = await apiFetch(`/api/operations/${operation.id}`);
      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Application status is unavailable.",
        );
      }
      if (!isOperationRecord(result)) {
        throw new Error("Application status response is incomplete.");
      }
      setOperation(result);
      if (
        result.state === "Applied" ||
        result.state === "Completed" ||
        result.state === "Succeeded"
      ) {
        await onApplied?.();
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Application status is unavailable.",
      );
    } finally {
      setStatusBusy(false);
    }
  }

  function open() {
    setOpened(true);
    setError("");
    setReview(null);
    setOperation(null);
    setAttempted(false);
    setApplyBusy(false);
    setStatusBusy(false);
    setRequestKey("");
    const next = action === "clone" ? "form" : "review";
    setStep(next);
    if (next === "review") void fetchReview();
  }

  function close() {
    reviewAbort.current?.abort();
    setOpened(false);
  }

  return (
    <>
      <button
        ref={trigger}
        className={`button compact ${action === "remove" ? "danger-outline" : ""}`}
        aria-label={`${copy.actionLabel} ${jobName}`}
        onClick={open}
      >
        {copy.actionLabel}
      </button>
      <dialog
        ref={dialog}
        className={`restore-confirm lifecycle-dialog ${action === "remove" ? "lifecycle-dialog-danger" : ""}`}
        aria-labelledby={title}
        onCancel={(event) => {
          if (applyBusy || statusBusy) {
            event.preventDefault();
            return;
          }
          close();
        }}
      >
        <div className="account-confirm">
          <h2 id={title}>{copy.title}</h2>
          <p className="mono">{jobName}</p>
          <p>{copy.description}</p>

          {step === "form" && (
            <form
              className="lifecycle-form"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void fetchReview();
              }}
            >
              <label className="auth-field">
                <span>New clone job name</span>
                <input
                  ref={cloneInput}
                  name="newJobName"
                  maxLength={80}
                  value={cloneName}
                  onChange={(event) => {
                    setCloneName(event.target.value);
                    setError("");
                    setReview(null);
                    setAttempted(false);
                  }}
                />
              </label>
              <p className="panel-footnote">
                The clone stays disabled by default. Identity, VM assignment,
                repository changes, and secret copying remain backend-owned and
                may be reported as unavailable by the review.
              </p>
              <div className="dialog-actions">
                <button
                  ref={primary}
                  className="button"
                  disabled={reviewBusy}
                  type="submit"
                >
                  {reviewBusy ? "Reviewing…" : copy.reviewLabel}
                </button>
                <button
                  className="button"
                  disabled={reviewBusy}
                  onClick={close}
                  type="button"
                >
                  Close
                </button>
              </div>
            </form>
          )}

          {step !== "form" && reviewBusy && (
            <p role="status">Checking current lifecycle evidence…</p>
          )}

          {error && (
            <p className="lifecycle-alert" role="alert">
              {error}
            </p>
          )}

          {step === "review" && (
            <div className="lifecycle-review" role="status">
              {review && (
                <>
                  <div className="lifecycle-summary-grid">
                    <p>
                      <strong>Readiness</strong>
                      <span>{prettyState(review.readiness)}</span>
                    </p>
                    <p>
                      <strong>Execution</strong>
                      <span>
                        {review.executionSupported
                          ? "Supported"
                          : "Not available"}
                      </span>
                    </p>
                    <p>
                      <strong>Proof revision</strong>
                      <span>{review.proofRevision}</span>
                    </p>
                    <p>
                      <strong>Review digest</strong>
                      <span className="mono">{review.reviewDigest}</span>
                    </p>
                  </div>
                  <p>{review.summary}</p>

                  {review.blockers.length > 0 && (
                    <>
                      <h3>What blocks this action</h3>
                      <ul className="lifecycle-list">
                        {review.blockers.map((item) => (
                          <li key={`${item.code}-${item.summary}`}>
                            {item.summary}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  {review.impacts.length > 0 && (
                    <>
                      <h3>Reviewed impacts</h3>
                      <ul className="lifecycle-list">
                        {review.impacts.map((item) => (
                          <li key={`${item.code}-${item.summary}`}>
                            <strong>{item.severity || "info"}:</strong>{" "}
                            {item.summary}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}

                  {review.preserveBackupData === true && (
                    <p className="panel-footnote">
                      Backup data is kept. This action does not authorize data
                      deletion.
                    </p>
                  )}

                  {review.retainedObligations &&
                    review.retainedObligations.length > 0 && (
                      <>
                        <h3>Retained backup obligations</h3>
                        <ul className="lifecycle-list">
                          {review.retainedObligations.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </>
                    )}

                  {review.unsupportedChanges &&
                    review.unsupportedChanges.length > 0 && (
                      <>
                        <h3>Currently unavailable</h3>
                        <ul className="lifecycle-list">
                          {review.unsupportedChanges.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </>
                    )}

                  {review.draftPlan && (
                    <details className="lifecycle-details">
                      <summary>Draft plan</summary>
                      <pre>{formatJson(review.draftPlan)}</pre>
                    </details>
                  )}
                  {review.resourceOwnership && (
                    <details className="lifecycle-details">
                      <summary>Resource ownership</summary>
                      <pre>{formatJson(review.resourceOwnership)}</pre>
                    </details>
                  )}
                  {review.duplicateProtection && (
                    <details className="lifecycle-details">
                      <summary>Duplicate protection</summary>
                      <pre>{formatJson(review.duplicateProtection)}</pre>
                    </details>
                  )}
                  {review.retainedRecovery && (
                    <details className="lifecycle-details">
                      <summary>Retained recovery</summary>
                      <pre>{formatJson(review.retainedRecovery)}</pre>
                    </details>
                  )}
                  {review.retirementRecord && (
                    <details className="lifecycle-details">
                      <summary>Retirement record</summary>
                      <pre>{formatJson(review.retirementRecord)}</pre>
                    </details>
                  )}
                </>
              )}

              <div className="dialog-actions">
                {review ? (
                  <button
                    ref={primary}
                    className="button"
                    disabled={reviewBusy}
                    onClick={() => setStep("confirm")}
                  >
                    Continue
                  </button>
                ) : (
                  <button ref={primary} className="button" onClick={close}>
                    Close
                  </button>
                )}
                {review ? (
                  <button
                    className="button"
                    disabled={reviewBusy}
                    onClick={close}
                  >
                    Close
                  </button>
                ) : (
                  <button
                    className="button"
                    disabled={reviewBusy}
                    onClick={() => void fetchReview()}
                  >
                    Refresh review
                  </button>
                )}
                {review && action === "clone" && (
                  <button
                    className="button"
                    disabled={reviewBusy}
                    onClick={() => {
                      setReview(null);
                      setStep("form");
                    }}
                  >
                    Edit clone details
                  </button>
                )}
                {review && (
                  <button
                    className="button"
                    disabled={reviewBusy}
                    onClick={() => void fetchReview()}
                  >
                    Refresh review
                  </button>
                )}
              </div>
            </div>
          )}

          {step === "confirm" && review && (
            <div className="lifecycle-review">
              <p>
                Confirm <strong>{copy.confirmLabel.toLowerCase()}</strong> for{" "}
                <strong>{jobName}</strong>.
              </p>
              {action === "remove" ? (
                <p>
                  Delete configuration for <strong>{jobName}</strong>. Backup
                  data is kept, and this batch does not add data-deletion
                  capability.
                </p>
              ) : (
                <p>{review.summary}</p>
              )}
              <p className="mono">Request key: {requestKey}</p>
              {!canExecute && (
                <p className="panel-footnote">
                  Execution remains blocked until the backend reports candidate
                  readiness and execution support.
                </p>
              )}
              <div className="dialog-actions">
                <button
                  ref={primary}
                  className={`button ${action === "remove" ? "danger-solid" : ""}`}
                  disabled={!canExecute || applyBusy}
                  onClick={() => void apply()}
                >
                  {applyBusy ? "Submitting…" : copy.confirmLabel}
                </button>
                <button
                  className="button"
                  disabled={applyBusy}
                  onClick={() => setStep("review")}
                >
                  Go back
                </button>
              </div>
            </div>
          )}

          {step === "result" && (
            <div className="lifecycle-review">
              <p className="mono">Request key: {requestKey}</p>
              {operation ? (
                <>
                  <div className="lifecycle-summary-grid">
                    <p>
                      <strong>Operation</strong>
                      <span className="mono">{operation.id}</span>
                    </p>
                    <p>
                      <strong>Status</strong>
                      <span>{operation.state}</span>
                    </p>
                    <p>
                      <strong>Kind</strong>
                      <span>{operation.kind || "lifecycle"}</span>
                    </p>
                    <p>
                      <strong>Target</strong>
                      <span>{operation.target || jobName}</span>
                    </p>
                  </div>
                  {operation.parameters?.summary && (
                    <p>{operation.parameters.summary}</p>
                  )}
                  {operation.parameters?.message && (
                    <p>{operation.parameters.message}</p>
                  )}
                </>
              ) : (
                <p>
                  Delivery outcome is unknown. Reconcile application status
                  before sending another request.
                </p>
              )}
              <div className="dialog-actions">
                <button ref={primary} className="button" onClick={close}>
                  Close
                </button>
                <button
                  className="button"
                  disabled={!operation?.id || statusBusy}
                  onClick={() => void checkStatus()}
                >
                  {statusBusy ? "Checking…" : "Check application status"}
                </button>
              </div>
            </div>
          )}
        </div>
      </dialog>
    </>
  );
}
