"use client";
import { ActivePolicySettings } from "./active-policy";
import { NativeSelectField } from "./form-controls";
import { RestoreProgress } from "./restore-progress";
import { JobLifecycleAction } from "./job-lifecycle";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  Square,
  Archive,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Database,
  HardDrive,
  History,
  LayoutDashboard,
  ListChecks,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  X,
  AlertTriangle,
  CircleHelp,
  LockKeyhole,
} from "lucide-react";

import { DataTable, SearchField } from "./table-controls";
import { VMwareInventory } from "./vmware-inventory";

import { apiFetch } from "@/lib/api";
import { AccountMenu, UserSettings, useIdentity } from "./auth";

import { RecoveryInspection } from "./recovery-inspection";

import { SessionReport } from "./session-report";

import { DiscardDraftDialog, NavigationDraft } from "./draft-guard";

import { PolicySettings } from "./policy-settings";

import { AlertJournal } from "./alert-journal";

type Session = {
  id: number;
  name: string;
  client: string;
  type: string;
  level: string;
  status: string;
  code: string;
  started: string | null;
  ended: string | null;
  duration: string;
  bytes: number;
  files: number;
  errors: number;
  pool: string;
  metadataPruned: boolean;
};
type Job = {
  name: string;
  type: string;
  client: string;
  fileset: string;
  lifecycleState?: "active" | "disabled" | "retired";
  schedule: string;
  storage: string[];
  pool: string;
  enabled: boolean;
  level: string;
  latest: Session | null;
};
type Workload = {
  name: string;
  job: string;
  folder: string;
  proxy: string;
  storage: string[];
  schedule: string;
  evidence: string;
  latestBackup: Session | null;
  sessions: Session[];
  backupCount: number;
};
type Operation = {
  id: string;
  idempotency_key: string;
  kind: "run" | "cancel" | "restore" | "provision";
  target: string;
  state: string;
  job_id: number | null;
  parameters: {
    message?: string;
    sessionStatus?: string;
    summary?: string;
    requestedLevel?: "Full" | "Incremental";
    simulationOnly?: boolean;
    destination?: { vm_name?: string; host?: string; datastore?: string };
  };
  created_at: string;
  updated_at: string;
};
type ConfirmAction = {
  requestedLevel?: "Full" | "Incremental";
  kind: "run" | "cancel";
  target: string;
  key: string;
  level?: string;
};
type Snapshot = {
  director: { name: string; version: string };
  connection: string;
  syncedAt: string;
  sourceErrors: Record<string, string>;
  jobs: Job[];
  workloads: Workload[];
  sessions: Session[];
  storages: {
    name: string;
    address: string;
    port: number;
    mediaType: string;
    enabled: boolean;
    concurrency: number;
  }[];
  pools: {
    name: string;
    volumes: number;
    maxVolumes: number;
    retentionDays: number;
  }[];
  volumes: {
    name: string;
    storage: string;
    pool: string;
    status: string;
    bytes: number;
  }[];
  schedules: { name: string; enabled: boolean; rules: string[] }[];
  persistence?: {
    state: string;
    database?: string;
    workloads?: number;
    sessions?: number;
    auditEvents?: number;
    encrypted?: boolean;
    certificateValidated?: boolean;
    message?: string;
  };
  capabilities?: {
    controls?: boolean;
    operationJobs?: string[];
    onboardingUuids?: string[];
    readOnly?: boolean;
    provisioningApply?: boolean;
    directVMRestore?: boolean;
    activePolicyApply?: boolean;
    vmwareInventory?: boolean;
  };
  sessionTotal: number;
  sessionLimit: number;
};
const views = [
  { id: "overview", name: "Overview", icon: LayoutDashboard },
  { id: "jobs", name: "Jobs", icon: ListChecks },
  { id: "backups", name: "Backups", icon: Archive },
  { id: "infrastructure", name: "Infrastructure", icon: Server },
  { id: "history", name: "History", icon: History },
  { id: "settings", name: "Settings", icon: Settings },
  { id: "job-schedule", name: "Edit job schedule", icon: Clock3 },
];
const descriptions: Record<string, string> = {
  overview:
    "Monitor backup coverage, review exceptions, and inspect recent activity.",
  jobs: "Configured backup jobs and their latest recorded sessions.",
  backups: "VMware workloads and recorded backup evidence.",
  infrastructure: "VMware inventory, backup proxies, and repository resources.",
  history: "Backup and restore sessions retrieved from the Catalog.",
  settings: "Local integration status and available capabilities.",
  "job-schedule": "Review scheduling changes for one managed backup job.",
};
const date = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Makassar",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(new Date(value)) + " WITA"
    : "Not recorded";
const bytes = (n: number) => {
  if (!n) return "0 B";
  const i = Math.min(4, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${["B", "KB", "MB", "GB", "TB"][i]}`;
};
const tone = (s: string) =>
  ["Succeeded", "Completed", "Backup recorded", "Connected"].includes(s)
    ? "success"
    : ["Failed", "Canceled", "Offline"].includes(s)
      ? "danger"
      : ["Running", "Created", "Prepared", "Dispatching", "Accepted"].includes(
            s,
          )
        ? "info"
        : [
              "Warning",
              "No backup recorded",
              "Stale",
              "Partial",
              "Unknown",
            ].includes(s)
          ? "warning"
          : "neutral";
function Badge({ value }: { value: string }) {
  const Icon =
    tone(value) === "success"
      ? CheckCircle2
      : tone(value) === "warning" || tone(value) === "danger"
        ? AlertTriangle
        : CircleHelp;
  return (
    <span className={`badge ${tone(value)}`}>
      <Icon size={13} aria-hidden="true" />
      {value}
    </span>
  );
}
function ConnectionBanner({
  data,
  error,
  busy,
}: {
  data: Snapshot | null;
  error: string;
  busy: boolean;
}) {
  const issues = data ? Object.keys(data.sourceErrors) : [];
  if (!error && !issues.length && data?.connection !== "stale") return null;
  return (
    <div className="connection-banner" role="status">
      <AlertTriangle size={18} />
      <div>
        <strong>
          {data
            ? "Some monitoring data is unavailable"
            : "Unable to load Bareos data"}
        </strong>
        <p>
          {error || `Unavailable sources: ${issues.join(", ")}.`}{" "}
          {data &&
            `Last snapshot: ${date(data.syncedAt)}. Treat these values as incomplete or stale.`}{" "}
          {busy && "Retrying…"}
        </p>
      </div>
    </div>
  );
}

const settingsSections = [
  { id: "connections", name: "Connections" },
  { id: "users", name: "Users" },
  { id: "permissions", name: "Permissions" },
  { id: "notifications", name: "Notifications" },
  { id: "audit", name: "Audit" },
  { id: "policies", name: "Policies" },
];
const validSettingsSection = (value: string | null) =>
  settingsSections.some((section) => section.id === value)
    ? value!
    : "connections";

export default function BackupCenter() {
  const [view, setView] = useState("overview"),
    [query, setQuery] = useState(""),
    [page, setPage] = useState(1);
  const [data, setData] = useState<Snapshot | null>(null),
    [busy, setBusy] = useState(true),
    [error, setError] = useState("");
  const [settingsSection, setSettingsSection] = useState("connections");
  const identity = useIdentity();
  const dirty = useRef(false);
  const [pendingNavigation, setPendingNavigation] =
    useState<NavigationDraft | null>(null);
  useEffect(() => {
    const listener = (e: Event) => {
      dirty.current = Boolean((e as CustomEvent).detail);
    };
    window.addEventListener("backupcenter-draft", listener);
    return () => window.removeEventListener("backupcenter-draft", listener);
  }, []);
  const [recoveryJob, setRecoveryJob] = useState<number | null>(null);
  const [mediaPage, setMediaPage] = useState(1);
  const [auditEvents, setAuditEvents] = useState<
    {
      id: number;
      actor: string;
      event_type: string;
      details: Record<string, unknown>;
      created_at: string;
    }[]
  >([]);
  const [auditError, setAuditError] = useState("");
  const [auditBusy, setAuditBusy] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [operationError, setOperationError] = useState("");
  const [operationPage, setOperationPage] = useState(1);
  const [confirmation, setConfirmation] = useState<ConfirmAction | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [levelLocked, setLevelLocked] = useState(false);
  const [actionError, setActionError] = useState("");
  const [trackedRestore, setTrackedRestore] = useState<number | null>(null);
  const [lastOperation, setLastOperation] = useState<Operation | null>(null);
  const confirmationDialog = useRef<HTMLDialogElement>(null);
  const confirmationBack = useRef<HTMLButtonElement>(null);
  const confirmationOpener = useRef<HTMLElement | null>(null);
  const submitLock = useRef(false);
  const [selected, setSelected] = useState<Session | null>(null),
    [logs, setLogs] = useState<{ time: string | null; text: string }[]>([]),
    [logBusy, setLogBusy] = useState(false),
    [logError, setLogError] = useState("");
  const request = useRef<AbortController | null>(null),
    opener = useRef<HTMLElement | null>(null),
    drawer = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const read = () => {
      const q = new URLSearchParams(location.search);
      setView(
        views.some((v) => v.id === q.get("view")) ? q.get("view")! : "overview",
      );
      setSettingsSection(validSettingsSection(q.get("section")));
      setQuery(q.get("q") || "");
      setPage(Math.max(1, Number(q.get("page")) || 1));
    };
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, []);
  const navigate = (
    nextView: string,
    nextQuery = query,
    nextPage = 1,
    section = settingsSection,
  ) => {
    if (
      dirty.current &&
      (nextView !== view ||
        (nextView === "settings" && section !== settingsSection))
    ) {
      setPendingNavigation({
        view: nextView,
        query: nextQuery,
        page: nextPage,
        section,
      });
      return;
    }
    setSettingsSection(validSettingsSection(section));
    setView(nextView);
    setQuery(nextQuery);
    setPage(nextPage);
    if (nextQuery !== query || nextView !== view) setMediaPage(1);
    const q = new URLSearchParams({ view: nextView });
    if (nextView === view && view === "infrastructure") {
      const current = new URLSearchParams(location.search);
      for (const key of ["invq", "invfolder", "invpage", "invsort"]) {
        const value = current.get(key);
        if (value) q.set(key, value);
      }
    }
    if (nextView === "settings")
      q.set("section", validSettingsSection(section));
    if (nextQuery) q.set("q", nextQuery);
    if (nextPage > 1) q.set("page", String(nextPage));
    history.replaceState(null, "", `?${q}`);
  };
  const refresh = useCallback(async (force = false) => {
    request.current?.abort();
    const c = new AbortController();
    request.current = c;
    setBusy(true);
    try {
      const r = await apiFetch(`/api/snapshot${force ? "?refresh=true" : ""}`, {
        signal: c.signal,
        cache: "no-store",
      });
      if (!r.ok)
        throw new Error(
          "Cannot connect to Bareos. Check the backend, network, and API settings.",
        );
      const d = await r.json();
      if (!c.signal.aborted) {
        setData(d);
        setError("");
      }
    } catch (e) {
      if (!c.signal.aborted) {
        setError(e instanceof Error ? e.message : "Connection failed.");
        setData((previous) =>
          previous ? { ...previous, connection: "stale" } : null,
        );
      }
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 60000);
    return () => {
      clearInterval(timer);
      request.current?.abort();
    };
  }, [refresh]);
  useEffect(() => {
    if (!selected) return;
    const c = new AbortController();
    setLogs([]);
    setLogBusy(true);
    setLogError("");
    drawer.current?.showModal();
    void fetch(`/api/sessions/${selected.id}/logs`, { signal: c.signal })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            "Unable to retrieve this session log. Retry by reopening the session.",
          );
        return r.json();
      })
      .then((d) => setLogs(d.lines))
      .catch((e) => {
        if (!c.signal.aborted) setLogError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setLogBusy(false);
      });
    return () => c.abort();
  }, [selected]);
  useEffect(() => {
    if (view !== "settings" || settingsSection !== "audit") return;
    const controller = new AbortController();
    setAuditBusy(true);
    setAuditPage(1);
    setAuditError("");
    fetch("/api/audit", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            "Audit history is unavailable. Check the application database.",
          );
        return response.json();
      })
      .then((result) => {
        if (!controller.signal.aborted) setAuditEvents(result.events);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setAuditEvents([]);
          setAuditError(error.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setAuditBusy(false);
      });
    return () => controller.abort();
  }, [view, settingsSection, data?.syncedAt]);
  useEffect(() => {
    if (!confirmation) return;
    confirmationDialog.current?.showModal();
    confirmationBack.current?.focus();
  }, [confirmation?.key]);
  const loadOperations = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await apiFetch("/api/operations", {
        signal,
        cache: "no-store",
      });
      if (!response.ok)
        throw new Error(
          "Operation journal unavailable. Run and Cancel are blocked until it recovers.",
        );
      const result = await response.json();
      if (signal?.aborted) return;
      setOperations(result.operations);
      setOperationError("");
      setLastOperation((previous) =>
        previous
          ? result.operations.find((o: Operation) => o.id === previous.id) ||
            previous
          : null,
      );
    } catch (error) {
      if (!signal?.aborted)
        setOperationError(
          error instanceof Error
            ? error.message
            : "Operation journal unavailable.",
        );
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void loadOperations(controller.signal);
    const interval = setInterval(() => {
      if (!document.hidden) void loadOperations(controller.signal);
    }, 5000);
    return () => {
      controller.abort();
      clearInterval(interval);
    };
  }, [loadOperations]);
  useEffect(() => {
    if (
      lastOperation?.kind === "restore" &&
      !lastOperation.job_id &&
      ["Prepared", "Dispatching"].includes(lastOperation.state)
    ) {
      setTrackedRestore(null);
      return;
    }
    const id =
      lastOperation?.kind === "restore"
        ? lastOperation.job_id
        : operations.find(
            (o) =>
              o.kind === "restore" &&
              o.job_id &&
              ["Accepted", "Running"].includes(o.state),
          )?.job_id;
    if (id) setTrackedRestore(id);
  }, [operations, lastOperation]);
  const activeOperation = (kind: string, target: string) =>
    operations.some(
      (o) =>
        o.kind === kind &&
        o.target === target &&
        !["Completed", "Failed"].includes(o.state),
    );
  const jobInScope = (name: string) =>
    !data?.capabilities?.operationJobs ||
    data.capabilities.operationJobs.includes(name);
  const controlsReady =
    !!data?.capabilities?.controls &&
    data?.connection === "connected" &&
    data?.persistence?.state === "connected" &&
    !operationError;
  const askConfirmation = (
    kind: "run" | "cancel",
    target: string,
    level?: string,
  ) => {
    if (!controlsReady || activeOperation(kind, target)) return;
    confirmationOpener.current = document.activeElement as HTMLElement;
    setActionError("");
    setLevelLocked(false);
    setConfirmation({ kind, target, level, key: crypto.randomUUID() });
  };
  const closeConfirmation = () => {
    if (submitLock.current) return;
    confirmationDialog.current?.close();
    setConfirmation(null);
    confirmationOpener.current?.focus();
  };
  const submitAction = async () => {
    if (!confirmation || submitLock.current) return;
    submitLock.current = true;
    setLevelLocked(true);
    setSubmitting(true);
    setActionError("");
    try {
      const response = await apiFetch("/api/operations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Backup-Center-Action": "confirmed",
        },
        body: JSON.stringify({
          ...(confirmation.kind === "run" && confirmation.requestedLevel
            ? { level: confirmation.requestedLevel }
            : {}),
          kind: confirmation.kind,
          target: confirmation.target,
          idempotency_key: confirmation.key,
          confirmed: true,
        }),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Operation could not be queued.",
        );
      setLastOperation(result);
      await loadOperations();
      submitLock.current = false;
      setSubmitting(false);
      closeConfirmation();
      void refresh(true);
    } catch (error) {
      setActionError(
        error instanceof Error
          ? error.message
          : "Request outcome could not be confirmed. Check the operation journal before retrying.",
      );
      // Keep this confirmation's idempotency key for any explicit retry.
      submitLock.current = false;
      setSubmitting(false);
      void loadOperations();
    }
  };
  useEffect(() => {
    if (identity?.role === "Viewer" && !submitLock.current) {
      confirmationDialog.current?.close();
      setConfirmation(null);
      confirmationOpener.current?.focus();
    }
  }, [identity?.role]);
  const open = (s: Session) => {
    opener.current = document.activeElement as HTMLElement;
    setSelected(s);
  };
  const close = () => {
    drawer.current?.close();
    setSelected(null);
    opener.current?.focus();
  };
  const matches = (value: unknown) =>
    JSON.stringify(value).toLowerCase().includes(query.toLowerCase());
  const restoreDestination = (s: Session) =>
    s.type === "Restore"
      ? operations.find((o) => o.kind === "restore" && o.job_id === s.id)
          ?.parameters.destination?.vm_name
      : undefined;
  const sessionLink = (s: Session) => (
    <button className="text-button" onClick={() => open(s)}>
      {restoreDestination(s) || s.name}
      <ArrowUpRight size={14} />
    </button>
  );
  const historyRows = (data?.sessions || [])
    .filter((s) => matches(s) || matches(restoreDestination(s) || ""))
    .map((s) => [
      sessionLink(s),
      <span className="mono">#{s.id}</span>,
      <Badge value={s.status} />,
      s.type,
      s.level || "—",
      date(s.started),
      s.duration,
      bytes(s.bytes),
    ]);
  const pending = (data?.workloads || []).filter(
    (w) => w.evidence !== "Backup recorded",
  );
  const status =
    data?.connection === "connected"
      ? "Connected"
      : data?.connection === "partial"
        ? "Partial"
        : data
          ? "Stale"
          : "Offline";
  return (
    <div className="app-shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <ShieldCheck size={23} />
          </div>
          <div>
            Backup Center<small>BAREOS OPERATIONS</small>
          </div>
        </div>
        <div className="workspace">
          <span className="workspace-icon">
            <Database size={18} />
          </span>
          <div>
            Main environment
            <small>{data?.director.name || "Bareos Director"}</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {views
            .filter((v) => v.id !== "job-schedule")
            .map((v) => (
              <a
                key={v.id}
                href={`?view=${v.id}`}
                aria-label={v.name}
                aria-current={
                  view === v.id || (view === "job-schedule" && v.id === "jobs")
                    ? "page"
                    : undefined
                }
                className={
                  view === v.id || (view === "job-schedule" && v.id === "jobs")
                    ? "active"
                    : ""
                }
                onClick={(e) => {
                  e.preventDefault();
                  navigate(v.id, "");
                }}
              >
                <v.icon size={18} aria-hidden="true" />
                {v.name}
                {v.id === "jobs" && data && <span>{data.jobs.length}</span>}
                {v.id === "backups" && data && (
                  <span>{data.workloads.length}</span>
                )}
              </a>
            ))}
        </nav>
        {view === "settings" && (
          <nav className="settings-subnav" aria-label="Settings navigation">
            {settingsSections.map((section) => (
              <a
                key={section.id}
                href={`?view=settings&section=${section.id}`}
                aria-current={
                  settingsSection === section.id ? "page" : undefined
                }
                className={settingsSection === section.id ? "active" : ""}
                onClick={(event) => {
                  event.preventDefault();
                  navigate("settings", "", 1, section.id);
                }}
              >
                {section.name}
              </a>
            ))}
          </nav>
        )}
        <div className="sidebar-bottom">
          <LockKeyhole size={16} />
          <div>
            Local operations<small>Confirmed actions · Local workspace</small>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="environment-dot" />
            Main environment <span className="top-separator">/</span>
            <span className="muted">
              {views.find((v) => v.id === view)?.name}
            </span>
          </div>
          <div>
            <span className="timezone">Asia/Makassar · UTC+08</span>
            <AccountMenu />
            <span className="avatar" aria-label="Local operator">
              LO
            </span>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">OPERATIONS CONSOLE</div>
              <h1>{views.find((v) => v.id === view)?.name}</h1>
              <p>{descriptions[view]}</p>
            </div>
            <button
              className="button"
              onClick={() => void refresh(true)}
              disabled={busy}
            >
              <RefreshCw size={16} className={busy ? "spinning" : ""} />
              {busy ? "Refreshing" : "Refresh"}
            </button>
          </div>
          <div className="sync-line">
            <Badge value={status} />
            <span>
              {data
                ? `Snapshot ${date(data.syncedAt)}`
                : "Connecting to the existing Bareos API…"}
            </span>
            <span className="read-only">
              {controlsReady ? "Local operator" : "Monitoring only"}
            </span>
          </div>
          <ConnectionBanner data={data} error={error} busy={busy} />
          {operationError && (
            <div className="connection-banner" role="status">
              <LockKeyhole size={18} />
              <div>
                <strong>Controls unavailable</strong>
                <p>{operationError}</p>
              </div>
            </div>
          )}
          {lastOperation && (
            <div className="operation-feedback" role="status">
              <Badge value={lastOperation.state} />
              <div>
                <strong>
                  {lastOperation.kind === "run"
                    ? "Run request"
                    : lastOperation.kind === "restore"
                      ? "Restore request"
                      : lastOperation.kind === "provision"
                        ? "Onboarding rehearsal"
                        : "Cancel request"}
                  : {lastOperation.parameters.summary || lastOperation.target}
                </strong>
                <p>
                  {lastOperation.parameters.message ||
                    "Queued for validation and dispatch."}
                </p>
                {lastOperation.kind === "run" &&
                  lastOperation.parameters.requestedLevel && (
                    <p>
                      Requested backup level:{" "}
                      {lastOperation.parameters.requestedLevel}
                    </p>
                  )}
                <small>
                  Operation {lastOperation.id}
                  {lastOperation.job_id
                    ? ` · Job #${lastOperation.job_id}`
                    : ""}
                </small>
              </div>
              <button
                className="text-button"
                onClick={() => navigate("history", "")}
              >
                View journal
                <ArrowUpRight size={14} />
              </button>
            </div>
          )}
          {trackedRestore && selected?.type !== "Restore" ? (
            <RestoreProgress jobId={trackedRestore} />
          ) : null}
          {data?.persistence?.state === "unavailable" && (
            <div className="connection-banner" role="status">
              <Database size={18} />
              <div>
                <strong>Persistence unavailable</strong>
                <p>{data.persistence.message}</p>
              </div>
            </div>
          )}
          {!data ? (
            <section className="initial-state" aria-live="polite">
              <Database size={34} />
              <h2>
                {busy
                  ? "Reading your backup environment"
                  : "Connection needs attention"}
              </h2>
              <p>
                {busy
                  ? "Fetching job definitions, sessions, and storage metadata."
                  : "Start the backend and verify API connectivity, then select Refresh."}
              </p>
            </section>
          ) : (
            <>
              {view === "overview" && (
                <div className="overview-dashboard">
                  <div className="metrics">
                    <Metric
                      label="VMware workloads"
                      value={String(data.workloads.length)}
                      note="Configured for backup"
                      icon={<Server size={20} />}
                    />
                    <Metric
                      label="Backup evidence"
                      value={`${data.workloads.filter((w) => w.evidence === "Backup recorded").length} / ${data.workloads.length}`}
                      note="VMs with successful records"
                      icon={<ShieldCheck size={20} />}
                    />
                    <Metric
                      label="Coverage review"
                      value={String(pending.length)}
                      note="Missing or unknown evidence"
                      icon={<AlertTriangle size={20} />}
                    />
                    <Metric
                      label="Data transferred"
                      value={bytes(
                        data.sessions
                          .filter(
                            (s) =>
                              s.type === "Backup" &&
                              ["Succeeded", "Warning"].includes(s.status),
                          )
                          .reduce((n, s) => n + s.bytes, 0),
                      )}
                      note="Successful backup sessions"
                      icon={<HardDrive size={20} />}
                    />
                  </div>
                  <section className="panel timeline-panel">
                    <div className="section-heading">
                      <div>
                        <h2>Protection timeline</h2>
                        <p>
                          Backup sessions per workload · latest on the right
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("backups", "")}
                      >
                        View backups
                        <ArrowUpRight size={15} />
                      </button>
                    </div>
                    <div className="timeline-legend">
                      <span>
                        <i className="dot success" />
                        Succeeded
                      </span>
                      <span>
                        <i className="dot warning" />
                        Warning
                      </span>
                      <span>
                        <i className="dot danger" />
                        Failed
                      </span>
                      <span>
                        <i className="dot neutral" />
                        No session
                      </span>
                    </div>
                    <div className="timeline-list">
                      {data.workloads.map((w) => (
                        <div className="timeline-row" key={w.job}>
                          <div className="vm-name">
                            <Server size={17} />
                            <div>
                              <strong>{w.name}</strong>
                              <small>{w.folder}</small>
                            </div>
                          </div>
                          <div className="timeline-blocks">
                            {Array.from({ length: 8 }, (_, i) => {
                              const s = [...w.sessions].reverse().slice(-8);
                              const item = s[i - (8 - s.length)];
                              return item ? (
                                <button
                                  key={i}
                                  className={`timeline-cell ${tone(item.status)}`}
                                  title={`Job #${item.id} · ${item.status} · ${date(item.started)}`}
                                  aria-label={`${w.name} session ${item.id}, ${item.status}`}
                                  onClick={() => open(item)}
                                />
                              ) : (
                                <span
                                  key={i}
                                  className="timeline-cell neutral"
                                />
                              );
                            })}
                          </div>
                          <div className="timeline-evidence">
                            <Badge value={w.evidence} />
                            <small>
                              {w.latestBackup
                                ? date(w.latestBackup.ended)
                                : "No record in current history"}
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="panel-footnote">
                      Backup evidence only. Recovery readiness and policy
                      compliance have not been verified.
                    </div>
                  </section>
                  <>
                    <section className="panel attention-panel">
                      <div className="section-heading">
                        <div>
                          <h2>Needs attention</h2>
                          <p>Coverage gaps in the current snapshot</p>
                        </div>
                        <span className="count">{pending.length}</span>
                      </div>
                      {pending.length ? (
                        pending.map((w) => (
                          <div className="attention-item" key={w.name}>
                            <span className="attention-icon">
                              <Clock3 size={18} />
                            </span>
                            <div>
                              <strong>{w.name}</strong>
                              <p>
                                {w.evidence === "Unknown"
                                  ? "Session data is unavailable."
                                  : "No backup record in current history."}
                              </p>
                            </div>
                            <button
                              className="icon-button"
                              aria-label={`View ${w.name} backups`}
                              onClick={() => navigate("backups", w.name)}
                            >
                              <ArrowUpRight size={17} />
                            </button>
                          </div>
                        ))
                      ) : (
                        <div className="empty">
                          <CheckCircle2 />
                          <strong>No coverage gaps in retrieved history</strong>
                          <span>Policy freshness remains unverified.</span>
                        </div>
                      )}
                    </section>
                    <section className="panel schedule-panel">
                      <div className="section-heading">
                        <div>
                          <h2>Backup schedule</h2>
                          <p>Rules reported by the Director</p>
                        </div>
                        <Clock3 size={19} />
                      </div>
                      {data.schedules
                        .filter((s) => s.enabled)
                        .map((s) => (
                          <div className="schedule-card" key={s.name}>
                            <strong>{s.name}</strong>
                            <div className="schedule-time">
                              Server timezone: UTC
                            </div>
                            {s.rules.map((r) => (
                              <div className="schedule-rule" key={r}>
                                {r}
                              </div>
                            ))}
                          </div>
                        ))}
                      <div className="panel-footnote">
                        Schedule rules use UTC. 13:30 UTC = 21:30 WITA.
                      </div>
                      <div className="storage-note">
                        <HardDrive size={21} />
                        <div>
                          <strong>
                            {data.storages.length} logical storage resources
                          </strong>
                          <p>
                            Resource count does not equal physical repository
                            count. Capacity telemetry is unavailable.
                          </p>
                        </div>
                      </div>
                    </section>
                  </>
                  <section className="panel activity-panel">
                    <div className="section-heading">
                      <div>
                        <h2>Recent activity</h2>
                        <p>
                          Most recent sessions in the retrieved Catalog data
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => navigate("history", "")}
                      >
                        View history
                        <ArrowUpRight size={15} />
                      </button>
                    </div>
                    <DataTable
                      headers={["Job", "Result", "Started", "Transferred"]}
                      rows={data.sessions
                        .slice(0, 5)
                        .map((session) => [
                          sessionLink(session),
                          <Badge value={session.status} />,
                          date(session.started),
                          bytes(session.bytes),
                        ])}
                      page={1}
                      setPage={() => {}}
                      empty="No recorded sessions"
                    />
                  </section>
                </div>
              )}
              {view !== "overview" &&
                view !== "settings" &&
                view !== "job-schedule" && (
                  <div className="view-toolbar">
                    <SearchField
                      value={query}
                      onChange={(v) => navigate(view, v)}
                    />
                    <span>
                      {view === "history"
                        ? `Catalog total: ${data.sessionTotal} · retrieval limit: ${data.sessionLimit}`
                        : "Live Bareos metadata"}
                    </span>
                  </div>
                )}
              {view === "jobs" && (
                <DataTable
                  headers={[
                    "Job",
                    "Type",
                    "Proxy / client",
                    "Schedule",
                    "Repository resource",
                    "Latest result",
                    "Actions",
                  ]}
                  rows={data.jobs.filter(matches).map((j) => {
                    const lifecycleState =
                      j.lifecycleState || (j.enabled ? "active" : "disabled");
                    const lifecycleLabel =
                      lifecycleState === "retired"
                        ? "Retired"
                        : lifecycleState === "disabled"
                          ? "Disabled"
                          : "Active";
                    return [
                      <div>
                        <strong>{j.name}</strong>
                        <small>
                          {lifecycleLabel} config · {j.fileset}
                        </small>
                      </div>,
                      j.type,
                      j.client,
                      j.schedule,
                      j.storage.join(", ") || "—",
                      j.latest ? (
                        <button
                          className="badge-button"
                          onClick={() => open(j.latest!)}
                        >
                          <Badge value={j.latest.status} />
                        </button>
                      ) : (
                        <Badge value="Not recorded" />
                      ),
                      <div className="row-actions">
                        {identity?.role === "Admin" &&
                          j.type === "Backup" &&
                          j.name.startsWith("VMware-") && (
                            <>
                              <JobLifecycleAction
                                key={`disable:${j.name}`}
                                action="disable"
                                jobName={j.name}
                                onApplied={() => refresh(true)}
                              />
                              <JobLifecycleAction
                                key={`enable:${j.name}`}
                                action="enable"
                                jobName={j.name}
                                onApplied={() => refresh(true)}
                              />
                            </>
                          )}
                        {identity?.role === "Admin" &&
                          j.type === "Backup" &&
                          j.name.startsWith("VMware-") && (
                            <JobLifecycleAction
                              key={`clone:${j.name}`}
                              action="clone"
                              jobName={j.name}
                              onApplied={() => refresh(true)}
                            />
                          )}
                        {identity?.role === "Admin" &&
                          j.type === "Backup" &&
                          j.name.startsWith("VMware-") && (
                            <JobLifecycleAction
                              key={`remove:${j.name}`}
                              action="remove"
                              jobName={j.name}
                              onApplied={() => refresh(true)}
                            />
                          )}
                        {identity?.role === "Admin" &&
                          j.type === "Backup" &&
                          jobInScope(j.name) && (
                            <button
                              className="button compact"
                              aria-label={`Edit schedule for ${j.name}`}
                              onClick={() => navigate("job-schedule", j.name)}
                            >
                              Edit schedule
                            </button>
                          )}
                        {j.type === "Backup" ? (
                          <button
                            className="button compact"
                            disabled={
                              !controlsReady ||
                              !j.enabled ||
                              !jobInScope(j.name) ||
                              (!!j.latest &&
                                [
                                  "Running",
                                  "Waiting",
                                  "Created",
                                  "Blocked",
                                ].includes(j.latest.status)) ||
                              j.type !== "Backup" ||
                              activeOperation("run", j.name) ||
                              !/^[A-Za-z0-9_.-]{1,128}$/.test(j.name)
                            }
                            aria-label={`Run ${j.name} now`}
                            onClick={() =>
                              askConfirmation("run", j.name, j.level)
                            }
                          >
                            <Play size={12} />
                            Run now
                          </button>
                        ) : (
                          <small>Restore template</small>
                        )}
                        {j.type === "Backup" &&
                          !activeOperation("run", j.name) &&
                          (!controlsReady ||
                            !j.enabled ||
                            !jobInScope(j.name) ||
                            (!!j.latest &&
                              [
                                "Running",
                                "Waiting",
                                "Created",
                                "Blocked",
                              ].includes(j.latest.status)) ||
                            !/^[A-Za-z0-9_.-]{1,128}$/.test(j.name)) && (
                            <small>
                              {!controlsReady
                                ? "Live connection required"
                                : !jobInScope(j.name)
                                  ? "Outside enabled operation scope"
                                  : !j.enabled
                                    ? "Job disabled"
                                    : !/^[A-Za-z0-9_.-]{1,128}$/.test(j.name)
                                      ? "Job name not supported"
                                      : "Session active"}
                            </small>
                          )}
                        {activeOperation("run", j.name) && (
                          <small>Operation pending</small>
                        )}
                      </div>,
                    ];
                  })}
                  page={page}
                  setPage={(v) => navigate(view, query, v)}
                  empty="No matching jobs"
                />
              )}
              {view === "backups" && (
                <>
                  <div className="info-note">
                    <CircleHelp size={18} />
                    <span>
                      VMs are derived from configured FileSets. Inventory
                      associations remain provisional. Inspect recovery resolves
                      chain and media metadata; restored contents remain
                      unverified.
                    </span>
                  </div>
                  <DataTable
                    headers={[
                      "VM",
                      "Backup evidence",
                      "Latest recorded backup",
                      "Records",
                      "Proxy",
                      "Repository resource",
                      "Recovery",
                    ]}
                    rows={data.workloads.filter(matches).map((w) => [
                      <div>
                        <strong>{w.name}</strong>
                        <small>{w.folder}</small>
                      </div>,
                      <Badge value={w.evidence} />,
                      w.latestBackup ? (
                        <button
                          className="text-button"
                          onClick={() => open(w.latestBackup!)}
                        >
                          {date(w.latestBackup.ended)}
                          <ArrowUpRight size={14} />
                        </button>
                      ) : (
                        "Not recorded"
                      ),
                      w.backupCount,
                      w.proxy,
                      w.storage.join(", "),
                      <button
                        className="text-button"
                        disabled={
                          !w.latestBackup || data.connection !== "connected"
                        }
                        onClick={() => setRecoveryJob(w.latestBackup!.id)}
                      >
                        Inspect recovery
                      </button>,
                    ])}
                    page={page}
                    setPage={(v) => navigate(view, query, v)}
                    empty="No matching workloads"
                  />
                </>
              )}
              {view === "history" && (
                <>
                  <SessionReport />
                  <AlertJournal
                    onReview={(evidence) => open(evidence as Session)}
                  />
                  <DataTable
                    headers={[
                      "Job",
                      "JobId",
                      "Result",
                      "Type",
                      "Level",
                      "Started",
                      "Duration",
                      "Transferred",
                    ]}
                    rows={historyRows}
                    page={page}
                    setPage={(v) => navigate(view, query, v)}
                    empty="No matching sessions"
                  />
                  <section className="panel operation-journal">
                    <div className="section-heading">
                      <div>
                        <h2>Operation journal</h2>
                        <p>
                          User-confirmed requests · latest 100 · Unknown
                          requests are not resent
                        </p>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => void loadOperations()}
                      >
                        Refresh journal
                        <RefreshCw size={14} />
                      </button>
                    </div>
                    <DataTable
                      headers={[
                        "Action / target",
                        "State",
                        "JobId",
                        "Requested",
                        "Outcome",
                      ]}
                      rows={operations.map((o) => [
                        `${o.kind === "run" ? "Run" : o.kind === "restore" ? "Restore" : o.kind === "provision" ? (o.parameters.simulationOnly === false ? "Enable backup" : "Onboarding rehearsal") : "Cancel"} · ${o.parameters.summary || o.target}`,
                        <Badge value={o.state} />,
                        o.job_id
                          ? `#${o.job_id}`
                          : o.kind === "provision"
                            ? "Not applicable"
                            : "Not confirmed",
                        date(o.created_at),
                        <span className="operation-message">
                          {o.parameters.message || "Queued"}
                        </span>,
                      ])}
                      page={operationPage}
                      setPage={setOperationPage}
                      empty="No operation requests"
                    />
                  </section>
                </>
              )}
              {view === "infrastructure" && (
                <>
                  <VMwareInventory
                    storages={data.storages}
                    liveUuids={data.capabilities?.onboardingUuids || []}
                    onQueued={(operation) => {
                      setLastOperation(operation);
                      void loadOperations();
                    }}
                  />
                  <section className="panel">
                    <div className="section-heading">
                      <h2>Backup proxies</h2>
                      <Badge value="Configured" />
                    </div>
                    <div className="proxy-list">
                      {Array.from(
                        new Set(data.workloads.map((w) => w.proxy)),
                      ).map((proxy) => (
                        <div className="proxy-card" key={proxy}>
                          <Server size={26} />
                          <div>
                            <strong>{proxy}</strong>
                            <p>
                              {
                                data.workloads.filter((w) => w.proxy === proxy)
                                  .length
                              }{" "}
                              configured VMware workloads
                            </p>
                            <small>Connection health not measured</small>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                  <h2 className="standalone-heading">
                    Logical storage resources
                  </h2>
                  <DataTable
                    headers={[
                      "Resource",
                      "Daemon endpoint",
                      "Media type",
                      "Concurrency",
                    ]}
                    rows={data.storages.filter(matches).map((s) => [
                      <strong>{s.name}</strong>,
                      <span className="mono">
                        {s.address}:{s.port}
                      </span>,
                      s.mediaType,
                      s.concurrency,
                    ])}
                    page={page}
                    setPage={(v) => navigate(view, query, v)}
                    empty="No matching storage resources"
                  />
                  <h2 className="standalone-heading">Recorded media</h2>
                  <DataTable
                    headers={[
                      "Volume",
                      "Pool",
                      "Storage",
                      "Status",
                      "Written bytes",
                    ]}
                    rows={data.volumes
                      .filter(matches)
                      .map((v) => [
                        v.name,
                        v.pool,
                        v.storage,
                        v.status,
                        bytes(v.bytes),
                      ])}
                    page={mediaPage}
                    setPage={setMediaPage}
                    empty="No matching media"
                  />
                </>
              )}
              {view === "job-schedule" && (
                <>
                  <button
                    className="button"
                    onClick={() => navigate("jobs", "")}
                  >
                    Back to Jobs
                  </button>
                  {identity?.role === "Admin" && jobInScope(query) ? (
                    <ActivePolicySettings key={query} jobName={query} />
                  ) : (
                    <p role="alert">
                      Select an approved job as an Admin to edit its schedule.
                    </p>
                  )}
                </>
              )}
              {view === "settings" && (
                <>
                  <div className="section-heading">
                    <h2>
                      Settings /{" "}
                      {
                        settingsSections.find(
                          (section) => section.id === settingsSection,
                        )?.name
                      }
                    </h2>
                  </div>
                  {settingsSection === "users" && <UserSettings />}
                  {settingsSection === "policies" && (
                    <>
                      {identity?.role === "Admin" && <ActivePolicySettings />}
                      <PolicySettings storages={data.storages} />
                    </>
                  )}
                  {settingsSection === "notifications" && (
                    <section className="panel">
                      <h2>Notifications</h2>
                      <p>
                        Notification delivery is not configured. Backup alerts
                        remain available in Overview; email and webhook delivery
                        are not implemented.
                      </p>
                    </section>
                  )}
                  {(settingsSection === "connections" ||
                    settingsSection === "permissions") && (
                    <>
                      <div className="settings-grid">
                        {settingsSection === "connections" && (
                          <section className="panel">
                            <div className="section-heading">
                              <h2>Connection</h2>
                              <Badge value={status} />
                            </div>
                            <dl>
                              <dt>Director</dt>
                              <dd>{data.director.name}</dd>
                              <dt>Bareos version</dt>
                              <dd>{data.director.version}</dd>
                              <dt>Transport</dt>
                              <dd>HTTPS · certificate verification enabled</dd>
                              <dt>Display timezone</dt>
                              <dd>Asia/Makassar (WITA)</dd>
                              <dt>Server timestamps</dt>
                              <dd>UTC</dd>
                              <dt>Refresh interval</dt>
                              <dd>60 seconds while visible</dd>
                            </dl>
                          </section>
                        )}
                        {settingsSection === "permissions" && (
                          <section className="panel">
                            <div className="section-heading">
                              <h2>Permissions and capabilities</h2>
                              <LockKeyhole size={18} />
                            </div>
                            <dl>
                              <dt>Monitoring</dt>
                              <dd>Enabled</dd>
                              <dt>Run / Cancel</dt>
                              <dd>
                                {controlsReady
                                  ? "Confirmed local operations"
                                  : "Unavailable"}
                              </dd>
                              <dt>Restore</dt>
                              <dd>
                                {identity?.role !== "Admin"
                                  ? "Admin-only"
                                  : data.capabilities?.directVMRestore
                                    ? "Direct VMware restore · approved source scope"
                                    : "Not enabled"}
                              </dd>
                              <dt>vCenter inventory</dt>
                              <dd>
                                {data.capabilities?.vmwareInventory
                                  ? "Inventory browsing available"
                                  : "Unavailable"}
                              </dd>
                              <dt>Add to backup</dt>
                              <dd>
                                {data.capabilities?.provisioningApply
                                  ? data.capabilities?.onboardingUuids?.length
                                    ? "Controlled apply for approved VMs"
                                    : "Dry-run rehearsal only"
                                  : "Not enabled"}
                              </dd>
                              <dt>User management</dt>
                              <dd>Local accounts and roles</dd>
                              <dt>Credentials</dt>
                              <dd>Backend only · not sent to the browser</dd>
                            </dl>
                          </section>
                        )}
                      </div>
                      {settingsSection === "connections" && (
                        <section className="panel">
                          <div className="section-heading">
                            <h2>Application database</h2>
                            <Badge
                              value={
                                data.persistence?.state === "connected"
                                  ? "Connected"
                                  : "Not available"
                              }
                            />
                          </div>
                          <dl>
                            <dt>Database</dt>
                            <dd>
                              {data.persistence?.database || "Not configured"}
                            </dd>
                            <dt>Transport</dt>
                            <dd>
                              {data.persistence?.encrypted
                                ? data.persistence.certificateValidated
                                  ? "TLS · certificate validation"
                                  : "TLS · certificate validation not enabled"
                                : "Not verified"}
                            </dd>
                            <dt>Stored workloads</dt>
                            <dd>{data.persistence?.workloads ?? "—"}</dd>
                            <dt>Observed sessions</dt>
                            <dd>{data.persistence?.sessions ?? "—"}</dd>
                            <dt>Audit events</dt>
                            <dd>{data.persistence?.auditEvents ?? "—"}</dd>
                            <dt>Recovery cache</dt>
                            <dd>
                              Last saved snapshot is restored after backend
                              restart and remains stale until refreshed.
                            </dd>
                          </dl>
                        </section>
                      )}
                    </>
                  )}
                  {settingsSection === "audit" && (
                    <section className="panel">
                      <div className="section-heading">
                        <div>
                          <h2>Collector audit history</h2>
                          <p>
                            Latest 100 persistence events · local collector
                            identity
                          </p>
                        </div>
                        <Database size={18} />
                      </div>
                      {auditBusy && (
                        <p className="panel-footnote" role="status">
                          Loading audit history…
                        </p>
                      )}
                      {auditError && (
                        <p className="connection-banner" role="alert">
                          {auditError}
                        </p>
                      )}
                      <DataTable
                        headers={[
                          "Event",
                          "Actor",
                          "Recorded",
                          "Observed data",
                        ]}
                        rows={auditEvents.map((event) => [
                          event.event_type,
                          event.actor,
                          date(event.created_at),
                          event.details.kind
                            ? `${event.details.kind} ${event.details.target} · ${event.details.state}`
                            : event.event_type.startsWith("identity.")
                              ? `${event.details.username} · ${event.details.role}`
                              : event.event_type.startsWith("auth.")
                                ? "Application session or password event"
                                : event.event_type.startsWith("policy.")
                                  ? `${event.details.name} · revision ${event.details.revision} · Draft`
                                  : `${event.details.workloads ?? "—"} workloads · ${event.details.sessions ?? "—"} sessions`,
                        ])}
                        page={auditPage}
                        setPage={setAuditPage}
                        empty="No audit events loaded"
                      />
                    </section>
                  )}
                </>
              )}
            </>
          )}
          <footer className="footer">
            <span>
              Backup Center <span className="muted">/</span> Bareos{" "}
              {data?.director.version || "—"}
            </span>
            <span>
              Local operations · Restore verification is recorded per test
            </span>
          </footer>
        </main>
      </div>
      <DiscardDraftDialog
        pending={pendingNavigation}
        onBack={() => setPendingNavigation(null)}
        onDiscard={() => {
          const next = pendingNavigation;
          dirty.current = false;
          setPendingNavigation(null);
          if (next) navigate(next.view, next.query, next.page, next.section);
        }}
      />
      <RecoveryInspection
        jobId={recoveryJob}
        onClose={() => setRecoveryJob(null)}
        onQueued={(operation) => {
          setLastOperation(operation as Operation);
          void loadOperations();
        }}
      />
      <dialog
        ref={drawer}
        className="session-dialog"
        aria-labelledby="session-title"
        onCancel={(e) => {
          e.preventDefault();
          close();
        }}
      >
        <div className="drawer-heading">
          <div>
            <div className="eyebrow">SESSION DETAILS</div>
            <h2 id="session-title">Job #{selected?.id}</h2>
          </div>
          <button
            autoFocus
            className="icon-button"
            aria-label="Close session details"
            onClick={close}
          >
            <X size={20} />
          </button>
        </div>
        {selected && (
          <>
            <h3>{restoreDestination(selected) || selected.name}</h3>
            {restoreDestination(selected) && <p>Bareos job: {selected.name}</p>}
            <Badge value={selected.status} />
            <dl>
              <dt>Started</dt>
              <dd>{date(selected.started)}</dd>
              <dt>Finished</dt>
              <dd>{date(selected.ended)}</dd>
              <dt>Type / level</dt>
              <dd>
                {selected.type} / {selected.level || "—"}
              </dd>
              <dt>Duration</dt>
              <dd>{selected.duration}</dd>
              <dt>Transferred</dt>
              <dd>{bytes(selected.bytes)}</dd>
              <dt>Files / errors</dt>
              <dd>
                {selected.files} / {selected.errors}
              </dd>
              <dt>Pool</dt>
              <dd>{selected.pool || "—"}</dd>
            </dl>
            {selected.type === "Backup" &&
              ["Running", "Waiting", "Created", "Blocked"].includes(
                selected.status,
              ) && (
                <div className="session-actions">
                  <button
                    className="button danger-outline"
                    disabled={
                      !controlsReady ||
                      !jobInScope(selected.name) ||
                      activeOperation("cancel", String(selected.id))
                    }
                    onClick={() =>
                      askConfirmation("cancel", String(selected.id))
                    }
                  >
                    <Square size={13} />
                    Cancel session
                  </button>
                  <small>
                    Stops this backup session; completed data may be incomplete.
                  </small>
                </div>
              )}
            {selected.type === "Restore" && (
              <RestoreProgress jobId={selected.id} />
            )}
            <h3>Session log</h3>
            {logBusy && <p role="status">Loading session log…</p>}
            {logError && (
              <p role="alert" className="log-error">
                {logError}
              </p>
            )}
            <div className="log-view">
              {logs.map((line, i) => (
                <div key={i}>
                  <time>{date(line.time)}</time>
                  <pre>{line.text}</pre>
                </div>
              ))}
              {!logBusy && !logError && !logs.length && (
                <p>No log entries recorded.</p>
              )}
            </div>
            <p className="muted">
              Up to 2,000 log entries. Successful execution does not establish
              restore verification.
            </p>
          </>
        )}
      </dialog>
      <dialog
        ref={confirmationDialog}
        className="confirmation-dialog"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-description"
        onCancel={(event) => {
          event.preventDefault();
          closeConfirmation();
        }}
      >
        <div className="confirmation-symbol">
          {confirmation?.kind === "cancel" ? (
            <Square size={22} />
          ) : (
            <Play size={22} />
          )}
        </div>
        <h2 id="confirmation-title">
          {confirmation?.kind === "cancel"
            ? "Cancel backup session?"
            : "Run backup now?"}
        </h2>
        <p id="confirmation-description">
          {confirmation?.kind === "cancel"
            ? `Request cancellation of Job #${confirmation.target}. This can leave an incomplete backup.`
            : `Start ${confirmation?.target}${confirmation?.requestedLevel ? ` at ${confirmation.requestedLevel} level` : " using its configured default level"} with its pre-job scripts. Bareos may promote an incremental request to Full if required.`}
        </p>
        {confirmation?.kind === "run" && (
          <NativeSelectField
            label="Backup level"
            value={confirmation.requestedLevel || ""}
            disabled={submitting || levelLocked}
            options={[
              { value: "", label: "Configured default" },
              { value: "Full", label: "Full" },
              { value: "Incremental", label: "Incremental" },
            ]}
            onChange={(value) =>
              setConfirmation((c) =>
                c
                  ? {
                      ...c,
                      requestedLevel: (value || undefined) as
                        "Full" | "Incremental" | undefined,
                    }
                  : c,
              )
            }
          />
        )}
        {confirmation?.level && (
          <p className="confirmation-detail">
            Configured level: {confirmation.level}
          </p>
        )}
        <p className="confirmation-detail">
          The request is recorded before dispatch. Closing the page does not
          cancel a queued operation.
        </p>
        {actionError && (
          <p className="log-error" role="alert">
            {actionError}
          </p>
        )}
        <div className="confirmation-actions">
          <button
            autoFocus
            ref={confirmationBack}
            className="button"
            disabled={submitting}
            onClick={closeConfirmation}
          >
            Go back
          </button>
          <button
            className={`button ${confirmation?.kind === "cancel" ? "danger-solid" : "primary-solid"}`}
            disabled={submitting || !controlsReady}
            onClick={() => void submitAction()}
          >
            {submitting
              ? "Queuing…"
              : confirmation?.kind === "cancel"
                ? "Cancel session"
                : "Run backup"}
          </button>
        </div>
      </dialog>
    </div>
  );
}
function Metric({
  label,
  value,
  note,
  icon,
}: {
  label: string;
  value: string;
  note: string;
  icon: React.ReactNode;
}) {
  return (
    <section className="metric">
      <div className="metric-top">
        <span>{label}</span>
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </section>
  );
}
