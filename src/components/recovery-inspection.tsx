"use client";
import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { actionHeaders, useIdentity } from "./auth";
import { apiFetch } from "@/lib/api";
import { DataTable } from "./table-controls";
type Recovery = {
  dispatchEnabled: boolean;
  sourceJobId: number;
  jobIds: number[];
  chain: {
    jobId: number;
    job: string;
    level: string;
    status: string;
    metadataPruned: boolean;
    media: { name: string; status: string }[];
  }[];
  items: { path: string; kind: string }[];
  blockers: string[];
  unsupported: string[];
  engineResolved: boolean;
  itemTotal: number;
  itemLimit: number;
};
export function RecoveryInspection({
  jobId,
  onClose,
  onQueued,
}: {
  jobId: number | null;
  onClose: () => void;
  onQueued: (operation: Record<string, unknown>) => void;
}) {
  const identity = useIdentity();
  const confirmation = useRef<HTMLDialogElement>(null),
    goBack = useRef<HTMLButtonElement>(null),
    start = useRef<HTMLButtonElement>(null),
    submitLock = useRef(false);
  const [requestKey, setRequestKey] = useState("");
  const [sending, setSending] = useState(false),
    [sendError, setSendError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null),
    opener = useRef<HTMLElement | null>(null),
    closeButton = useRef<HTMLButtonElement>(null);
  const [data, setData] = useState<Recovery | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [page, setPage] = useState(1),
    [chainPage, setChainPage] = useState(1),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    if (identity?.role !== "Admin" && !submitLock.current)
      confirmation.current?.close();
  }, [identity?.role]);
  useEffect(() => {
    if (!jobId) return;
    opener.current = document.activeElement as HTMLElement;
    dialog.current?.showModal();
    closeButton.current?.focus();
    return () => {
      confirmation.current?.close();
      dialog.current?.close();
      opener.current?.focus();
    };
  }, [jobId]);
  useEffect(() => {
    if (!jobId) return;
    const abort = new AbortController();
    setBusy(true);
    setData(null);
    setError("");
    setPage(1);
    setChainPage(1);
    apiFetch("/api/recovery/" + jobId, { signal: abort.signal })
      .then(async (r) => {
        const x = await r.json();
        if (!r.ok)
          throw new Error(
            typeof x.detail === "string"
              ? x.detail
              : "Recovery inspection failed.",
          );
        if (!abort.signal.aborted) setData(x);
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [jobId, retry]);
  return (
    <dialog
      ref={dialog}
      className="recovery-dialog"
      aria-labelledby="recovery-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="recovery-content">
        <div className="section-heading">
          <div>
            <h2 id="recovery-title">Recovery inspection</h2>
            <p>Backup JobId {jobId}</p>
          </div>
          <button
            className="icon-button"
            ref={closeButton}
            aria-label="Close recovery inspection"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        {busy && (
          <p role="status">Resolving backup dependencies and Catalog media…</p>
        )}
        {error && (
          <div role="alert">
            <p>{error}</p>
            <button className="button" onClick={() => setRetry((n) => n + 1)}>
              Retry inspection
            </button>
          </div>
        )}
        {data && (
          <>
            <div className="info-note">
              <span>
                {data.engineResolved
                  ? "Director resolved the dependency chain."
                  : "Dependency chain unavailable."}{" "}
                Media readability and restored contents have not been verified.
              </span>
            </div>
            <h3>Required backup chain</h3>
            <DataTable
              headers={["JobId", "Backup", "Level", "Result", "Required media"]}
              rows={data.chain.map((r) => [
                r.jobId,
                r.job,
                r.level,
                r.status,
                r.media.map((m) => m.name + " · " + m.status).join(", "),
              ])}
              page={chainPage}
              setPage={setChainPage}
              empty="No dependency chain available"
            />
            <h3>VMware recovery items</h3>
            <p>
              These are virtual disk/firmware backup items, not a browser for
              files inside the guest.
            </p>
            <DataTable
              headers={["Backup item", "Type"]}
              rows={data.items.map((i) => [i.path, i.kind])}
              page={page}
              setPage={setPage}
              empty="File metadata unavailable"
            />
            {data.itemTotal > data.itemLimit && (
              <p>
                Showing the first {data.itemLimit} items from {data.itemTotal}{" "}
                recorded items.
              </p>
            )}
            {!!data.blockers.length && (
              <div className="connection-banner" role="status">
                <div>
                  <strong>Recovery blockers</strong>
                  <ul>
                    {data.blockers.map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            <h3>Available recovery direction</h3>
            <p>
              Export VMware disks to a new isolated directory on the backup
              server. Overwrite: Never. Live export requires the
              administrator-approved test-job scope.
            </p>
            <p className="mono">
              /mnt/bareos-smb/backupcenter-restore-tests/&lt;request-id&gt;
            </p>
            <button
              className="button"
              ref={start}
              disabled={
                !data.dispatchEnabled ||
                data.blockers.length > 0 ||
                identity?.role !== "Admin"
              }
              onClick={() => {
                setRequestKey(crypto.randomUUID());
                setSendError("");
                confirmation.current?.showModal();
                goBack.current?.focus();
              }}
              aria-describedby="restore-unavailable"
            >
              Start restore
            </button>
            <p id="restore-unavailable">
              Isolated disk export is implemented. Live dispatch remains
              disabled until a test job and destination permissions are
              accepted.
            </p>
            <small>Unavailable modes: {data.unsupported.join(" · ")}</small>
          </>
        )}
      </div>
      <dialog
        ref={confirmation}
        className="restore-confirm"
        aria-labelledby="restore-confirm-title"
        onCancel={(e) => {
          if (submitLock.current) e.preventDefault();
        }}
        onClose={() => start.current?.focus()}
      >
        <div className="account-confirm">
          <h2 id="restore-confirm-title">Export VMware disks?</h2>
          <p>
            Recover all VMware disk/firmware items from backup JobId {jobId} and
            its required chain into a new isolated directory. This can use
            substantial repository space and I/O.
          </p>
          <p className="mono">
            /mnt/bareos-smb/backupcenter-restore-tests/{requestKey}
          </p>
          <p>
            Overwrite: Never. VM boot and recovered contents still require
            separate verification.
          </p>
          <div className="dialog-actions">
            <button
              className="button"
              ref={goBack}
              disabled={sending}
              onClick={() => confirmation.current?.close()}
            >
              Go back
            </button>
            <button
              className="button"
              disabled={
                sending || !data?.dispatchEnabled || identity?.role !== "Admin"
              }
              onClick={async () => {
                if (submitLock.current || !jobId) return;
                submitLock.current = true;
                setSending(true);
                setSendError("");
                try {
                  const response = await apiFetch("/api/operations", {
                    method: "POST",
                    headers: actionHeaders,
                    body: JSON.stringify({
                      kind: "restore",
                      target: String(jobId),
                      idempotency_key: requestKey,
                      confirmed: true,
                    }),
                  });
                  const row = await response.json();
                  if (!response.ok)
                    throw new Error(
                      typeof row.detail === "string"
                        ? row.detail
                        : "Restore request could not be queued.",
                    );
                  onQueued(row);
                  confirmation.current?.close();
                  onClose();
                } catch (e) {
                  setSendError(
                    e instanceof Error
                      ? e.message
                      : "Delivery outcome unknown. Check the operation journal before retrying.",
                  );
                } finally {
                  submitLock.current = false;
                  setSending(false);
                }
              }}
            >
              {sending ? "Queuing…" : "Export disks"}
            </button>
          </div>
          {sendError && <p role="alert">{sendError}</p>}
        </div>
      </dialog>
    </dialog>
  );
}
