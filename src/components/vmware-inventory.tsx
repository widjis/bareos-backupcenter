"use client";
import { useEffect, useRef, useState } from "react";
import { Folder, RefreshCw, Server, X } from "lucide-react";
import { DataTable, SearchField } from "./table-controls";

import { apiFetch } from "@/lib/api";

import { useIdentity } from "./auth";
import { OnboardingPreview } from "./onboarding-preview";

type VM = {
  id: string;
  name: string;
  moref: string;
  instanceUuid: string | null;
  folder: string;
  datacenter: string | null;
  power: string;
  host: string | null;
  cluster: string | null;
  cpu: number | null;
  memoryMb: number | null;
  template: boolean;
  association: string;
  job: string | null;
  backupEvidence: string;
};
type Node = { id: string; name: string; parent: string | null; kind: string };
type Inventory = {
  state: string;
  error: string | null;
  syncedAt: string | null;
  folders: Node[];
  vms: VM[];
  total: number;
  totalVisible: number;
  page: number;
  pages: number;
  pageSize: number;
  persistence?: string;
  scope: string;
};

function initial() {
  const p =
    typeof window === "undefined"
      ? new URLSearchParams()
      : new URLSearchParams(window.location.search);
  return {
    q: p.get("invq") || "",
    folder: p.get("invfolder") || "",
    page: Math.max(1, Number(p.get("invpage")) || 1),
    descending: p.get("invsort") === "desc",
  };
}
export function VMwareInventory({
  storages,
  onQueued,
  liveUuids = [],
}: {
  storages: { name: string; mediaType: string; enabled: boolean }[];
  liveUuids?: string[];
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
}) {
  const identity = useIdentity();
  const [previewIds, setPreviewIds] = useState<string[] | null>(null);
  const [filters, setFilters] = useState(initial);
  const [draft, setDraft] = useState(filters.q);
  const [composing, setComposing] = useState(false);
  const [data, setData] = useState<Inventory | null>(null);
  const [selected, setSelected] = useState<Record<string, VM>>({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const lastRefresh = useRef(0);
  const inputTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const change = (next: typeof filters) => {
    setFilters(next);
    const p = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries({
      invq: next.q,
      invfolder: next.folder,
      invpage: next.page > 1 ? String(next.page) : "",
      invsort: next.descending ? "desc" : "",
    })) {
      if (value) p.set(key, value);
      else p.delete(key);
    }
    window.history.replaceState(null, "", "?" + p.toString());
  };
  useEffect(() => {
    const restore = () => {
      const f = initial();
      setFilters(f);
      setDraft(f.q);
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);
  useEffect(() => {
    if (composing || draft === filters.q) return;
    inputTimer.current = setTimeout(
      () => change({ ...filters, q: draft, page: 1 }),
      draft ? 300 : 0,
    );
    return () => {
      if (inputTimer.current) clearTimeout(inputTimer.current);
    };
  }, [draft, composing, filters]);
  useEffect(() => {
    const abort = new AbortController();
    setBusy(true);
    setError("");
    const params = new URLSearchParams({
      q: filters.q,
      folder: filters.folder,
      page: String(filters.page),
      descending: String(filters.descending),
      refresh: String(refresh !== lastRefresh.current),
    });
    lastRefresh.current = refresh;
    apiFetch("/api/inventory?" + params, { signal: abort.signal })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            "Inventory service is unavailable. Retry the connection.",
          );
        const next: Inventory = await response.json();
        if (abort.signal.aborted) return;
        setData(next);
        if (next.page !== filters.page) change({ ...filters, page: next.page });
      })
      .catch((e) => {
        if (!abort.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [filters, refresh]);
  const nodes = data?.folders || [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const depth = (node: Node) => {
    let d = 0,
      parent = node.parent;
    const seen = new Set([node.id]);
    while (parent && byId.has(parent) && !seen.has(parent)) {
      seen.add(parent);
      d++;
      parent = byId.get(parent)!.parent;
    }
    return Math.min(d, 6);
  };
  const path = (node: Node) => {
    const names = [node.name],
      seen = new Set([node.id]);
    let parent = node.parent;
    while (parent && byId.has(parent) && !seen.has(parent)) {
      seen.add(parent);
      const n = byId.get(parent)!;
      names.unshift(n.name);
      parent = n.parent;
    }
    return names.join("/");
  };
  const count = Object.keys(selected).length;
  return (
    <section className="inventory-section" aria-labelledby="vmware-title">
      <div className="section-heading">
        <div>
          <h2 id="vmware-title">VMware inventory</h2>
          <p>
            {data?.totalVisible ?? "—"} visible virtual machines · read-only
            discovery
          </p>
        </div>
        <button
          className="button"
          disabled={busy}
          onClick={() => setRefresh((n) => n + 1)}
        >
          <RefreshCw size={15} aria-hidden="true" />
          Refresh inventory
        </button>
      </div>
      <div className="inventory-status" role="status">
        {busy
          ? "Loading VMware inventory…"
          : error || data?.error || "Inventory connected"}
        {data?.syncedAt && (
          <span>
            Last synchronized:{" "}
            {new Intl.DateTimeFormat("en-GB", {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: "Asia/Makassar",
            }).format(new Date(data.syncedAt))}{" "}
            WITA{data.state === "stale" || error ? " · Stale" : ""}
          </span>
        )}
        {data?.persistence === "unavailable" && (
          <span>
            Inventory database unavailable; this result is not persisted.
          </span>
        )}
      </div>
      <div className="inventory-layout">
        <nav
          className="inventory-tree panel"
          aria-label="VMware inventory folders"
        >
          <button
            className={!filters.folder ? "active" : ""}
            onClick={() => change({ ...filters, folder: "", page: 1 })}
          >
            <Server size={15} aria-hidden="true" />
            All visible VMs
          </button>
          {[...nodes]
            .sort((a, b) => path(a).localeCompare(path(b)))
            .map((node) => (
              <button
                key={node.id}
                className={filters.folder === node.id ? "active" : ""}
                style={{ paddingInlineStart: 12 + depth(node) * 12 }}
                onClick={() => change({ ...filters, folder: node.id, page: 1 })}
                title={path(node)}
                aria-current={filters.folder === node.id ? "true" : undefined}
              >
                <Folder size={15} aria-hidden="true" />
                <span>{node.name}</span>
              </button>
            ))}
        </nav>
        <div className="inventory-results" aria-busy={busy}>
          <div className="inventory-toolbar">
            <SearchField
              label="Search VMware inventory"
              value={draft}
              onComposition={setComposing}
              onChange={(v) => {
                setDraft(v);
                if (!v) {
                  if (inputTimer.current) clearTimeout(inputTimer.current);
                  change({ ...filters, q: "", page: 1 });
                }
              }}
            />
            <small>Search all visible VMs in the selected folder</small>
          </div>
          {data && data.state !== "unavailable" && (
            <DataTable
              headers={[
                "Virtual machine",
                "Location",
                "Compute",
                "Backup association",
                "Select",
              ]}
              page={data.page}
              setPage={(page) => change({ ...filters, page })}
              server={{
                total: data.total,
                size: data.pageSize,
                descending: filters.descending,
                sort: () =>
                  change({
                    ...filters,
                    descending: !filters.descending,
                    page: 1,
                  }),
              }}
              empty={
                filters.q
                  ? "No matching virtual machines"
                  : "No visible virtual machines"
              }
              rows={data.vms.map((vm) => [
                <div key="vm">
                  <strong>{vm.name}</strong>
                  <small className="inventory-detail">
                    {vm.power} · {vm.moref}
                    {vm.template ? " · Template" : ""}
                  </small>
                </div>,
                <div key="location">
                  {vm.datacenter || "Unknown datacenter"}
                  <small className="inventory-detail">{vm.folder}</small>
                </div>,
                <div key="compute">
                  {vm.host || "Host unavailable"}
                  <small className="inventory-detail">
                    {vm.cpu ?? "?"} CPU ·{" "}
                    {vm.memoryMb == null
                      ? "?"
                      : (vm.memoryMb / 1024).toFixed(1)}{" "}
                    GB RAM
                  </small>
                </div>,
                <div key="association">
                  {vm.association}
                  <small className="inventory-detail">
                    {vm.job || "No confirmed job mapping"}
                  </small>
                </div>,
                <input
                  key="select"
                  type="checkbox"
                  aria-label={"Select " + vm.name + " " + vm.moref}
                  checked={!!selected[vm.id]}
                  disabled={
                    busy ||
                    data.state !== "connected" ||
                    vm.template ||
                    !vm.instanceUuid
                  }
                  onChange={(e) =>
                    setSelected((old) => {
                      const next = { ...old };
                      if (e.target.checked) next[vm.id] = vm;
                      else delete next[vm.id];
                      return next;
                    })
                  }
                />,
              ])}
            />
          )}
          {!data && (
            <div className="empty">
              {error || "Connecting to VMware inventory…"}
            </div>
          )}
          {data?.state === "unavailable" && (
            <div className="empty">
              <strong>VMware inventory unavailable</strong>
              <span>
                Check connection settings and refresh. No empty inventory is
                inferred.
              </span>
            </div>
          )}
        </div>
      </div>
      <OnboardingPreview
        ids={previewIds}
        storages={storages}
        onQueued={onQueued}
        onClose={() => setPreviewIds(null)}
      />
      <div className="selection-summary" aria-live="polite">
        <div>
          <strong>
            {count} VM{count === 1 ? "" : "s"} selected
          </strong>
          <small>
            Explicit selections are retained across search and pages. Selection
            does not enroll a VM.
          </small>
        </div>
        <button
          className="button"
          disabled={!count}
          onClick={() => setSelected({})}
        >
          Clear selection
        </button>
        <button
          className="button"
          disabled={
            !count ||
            count > 25 ||
            data?.state !== "connected" ||
            busy ||
            identity?.role !== "Admin"
          }
          onClick={() => setPreviewIds(Object.keys(selected))}
        >
          Preview onboarding
        </button>
        <button
          className="button"
          disabled={
            count !== 1 ||
            !Object.values(selected).every(
              (vm) =>
                vm.instanceUuid &&
                liveUuids.includes(vm.instanceUuid) &&
                vm.association === "Unassigned",
            ) ||
            data?.state !== "connected" ||
            busy ||
            identity?.role !== "Admin"
          }
          onClick={() => setPreviewIds(Object.keys(selected))}
          aria-describedby="provisioning-reason"
        >
          Live Add to backup
        </button>
      </div>
      {!!count && (
        <ul className="selected-vms">
          {Object.values(selected).map((vm) => (
            <li key={vm.id}>
              {vm.name} · {vm.moref}
              <button
                aria-label={"Remove selection " + vm.name + " " + vm.moref}
                onClick={() =>
                  setSelected((old) => {
                    const next = { ...old };
                    delete next[vm.id];
                    return next;
                  })
                }
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="inventory-caption" id="provisioning-reason">
        Preview supports up to 25 selected VMs per batch for Admins. Live Add to
        backup is available only for a server-approved pilot VM. Other
        selections remain dry-run rehearsals. Candidate matches use current
        names and folders; they are not confirmed identity assignments.
        Visibility is limited to the configured VMware account.
      </p>
    </section>
  );
}
