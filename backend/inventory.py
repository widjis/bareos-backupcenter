"""Read-only vCenter inventory with certificate pinning and scoped identities."""
import asyncio
import re
import ssl
import time
from contextlib import closing
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from dotenv import dotenv_values
from psycopg2.extras import Json
from pyVim.connect import Connect, Disconnect
from pyVmomi import vim, vmodl

from backend.persistence import ROOT

class InventoryError(ValueError):
    """Safe operator-facing errors only."""


VM_PATHS = ["name", "parent", "config.instanceUuid", "config.uuid", "config.template", "config.hardware.numCPU", "config.hardware.memoryMB", "runtime.powerState", "runtime.host", "summary.storage.committed"]
TYPE_PATHS = [(vim.Datacenter, ["name", "parent", "vmFolder"]), (vim.Folder, ["name", "parent"]), (vim.VirtualApp, ["name", "parent"]), (vim.HostSystem, ["name", "parent"]), (vim.ClusterComputeResource, ["name", "parent"]), (vim.ComputeResource, ["name", "parent"]), (vim.VirtualMachine, VM_PATHS)]


def ref(value):
    return getattr(value, "_moId", None)


def entities(objects, connection):
    rows = {ref(o.obj): {p.name: p.val for p in o.propSet} for o in objects}
    kinds = {ref(o.obj): o.obj.__class__.__name__ for o in objects}
    folders = []
    vms = []
    for key, row in rows.items():
        if kinds[key] in ("vim.Datacenter", "vim.Folder", "vim.VirtualApp"):
            folders.append({"id": key, "name": row.get("name", key), "parent": ref(row.get("parent")), "kind": "datacenter" if kinds[key] == "vim.Datacenter" else "folder"})
        if kinds[key] != "vim.VirtualMachine":
            continue
        parent = ref(row.get("parent"))
        lineage, visited, dc = [], set(), None
        while parent in rows and parent not in visited:
            visited.add(parent)
            ancestor = rows[parent]
            if kinds[parent] == "vim.Datacenter":
                dc = {"id": parent, "name": ancestor.get("name", parent)}
                break
            lineage.append(parent)
            parent = ref(ancestor.get("parent"))
        # The datacenter's implicit vmFolder is not part of a plugin folder path.
        implicit = ref(rows.get(dc["id"], {}).get("vmFolder")) if dc else None
        path = "/" + "/".join(rows[p].get("name", p) for p in reversed(lineage) if p != implicit)
        uid = row.get("config.instanceUuid")
        host = rows.get(ref(row.get("runtime.host")), {})
        compute = rows.get(ref(host.get("parent")), {})
        identity = str(uuid5(NAMESPACE_URL, connection + ":" + (uid or key)))
        vms.append({"id": identity, "moref": key, "instanceUuid": uid, "biosUuid": row.get("config.uuid"), "name": row.get("name", key), "folderId": ref(row.get("parent")), "ancestorIds": lineage + ([dc["id"]] if dc else []), "folder": path, "datacenter": dc["name"] if dc else None, "power": str(row.get("runtime.powerState", "unknown")), "template": row.get("config.template", False), "cpu": row.get("config.hardware.numCPU"), "memoryMb": row.get("config.hardware.memoryMB"), "committedBytes": row.get("summary.storage.committed"), "host": host.get("name"), "cluster": compute.get("name"), "identityQuality": "instance-uuid" if uid else "moref-only"})
    ids=[v["id"] for v in vms]
    if len(ids) != len(set(ids)):
        raise InventoryError("Duplicate VMware instance identifiers; inventory requires review.")
    return folders, vms


def reconcile(vms, workloads, assignments=None):
    # Names/folders are only provisional associations, never a persisted identity binding.
    assignments = assignments or {}
    result = []
    for vm in vms:
        matches = [w for w in workloads if (w.get("instanceUuid") == vm["instanceUuid"] if w.get("instanceUuid") else w.get("name") == vm["name"] and w.get("datacenter") == vm["datacenter"] and w.get("folder", "/").rstrip("/") == vm["folder"].rstrip("/"))]
        unique = len(matches) == 1 and sum(v["name"] == vm["name"] and v["folder"] == vm["folder"] and v["datacenter"] == vm["datacenter"] for v in vms) == 1
        staged = assignments.get(vm["id"])
        association = ("Identity match" if matches[0].get("instanceUuid") else "Candidate match") if unique else "Ambiguous match" if matches else "Unassigned"
        job = matches[0]["job"] if unique else None
        evidence = matches[0].get("evidence", "Unknown") if unique else "Unknown"
        if staged and staged.get("state") == "Prepared":
            association = "Prepared assignment"
            job = staged.get("job_name")
            evidence = "Pending controlled apply"
        result.append({**vm, "association": association, "job": job, "backupEvidence": evidence})
    return result


class Inventory:
    def __init__(self, store):
        self.store = store
        self.values = dotenv_values(ROOT / ".env")
        endpoint = self.values.get("VMWARE_VCSERVER", "")
        parsed = urlparse(endpoint if "://" in endpoint else "https://" + endpoint)
        self.host = parsed.hostname
        self.port = parsed.port or 443
        self.valid_endpoint = parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.path in ("", "/")
        self.connection = str(uuid5(NAMESPACE_URL, "vcenter:https://" + str(self.host) + ":" + str(self.port)))
        self.lock = asyncio.Lock()
        self.cache = None
        self.last_attempt = float("-inf")

    def collect(self):
        pin = re.sub(":", "", self.values.get("VMWARE_VCTHUMBPRINT", "")).lower()
        if not self.valid_endpoint or not self.host or not all(self.values.get(k) for k in ("VMWARE_VCUSER", "VMWARE_VCPASS")):
            raise InventoryError("VMware inventory connection is not configured.")
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64}|[0-9a-f]{128})", pin):
            raise InventoryError("A valid VMware certificate fingerprint is required.")
        # SDK verifies this exact pin on every new socket BEFORE sending SOAP/login.
        # Connect (not SmartConnect) avoids an unpinned version-discovery HTTP request.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        si = Connect(host=self.host, port=self.port, user=self.values["VMWARE_VCUSER"], pwd=self.values["VMWARE_VCPASS"], version="vim.version.version9", thumbprint=pin, sslContext=context, httpConnectionTimeout=15)
        view = None
        try:
            content = si.RetrieveContent()
            view = content.viewManager.CreateContainerView(content.rootFolder, [x[0] for x in TYPE_PATHS], True)
            spec = vmodl.query.PropertyCollector.FilterSpec(objectSet=[vmodl.query.PropertyCollector.ObjectSpec(obj=view, skip=True, selectSet=[vmodl.query.PropertyCollector.TraversalSpec(name="inventory", type=vim.view.ContainerView, path="view", skip=False)])], propSet=[vmodl.query.PropertyCollector.PropertySpec(type=t, all=False, pathSet=p) for t, p in TYPE_PATHS])
            collector = content.propertyCollector
            page = collector.RetrievePropertiesEx([spec], vmodl.query.PropertyCollector.RetrieveOptions(maxObjects=250))
            objects = []
            started = time.monotonic()
            while page:
                # Reject incomplete/overlarge inventory instead of marking missing VMs removed.
                if any(getattr(o, "missingSet", None) for o in page.objects):
                    raise InventoryError("Inventory properties are inaccessible; check VMware read permissions.")
                objects.extend(page.objects)
                if len(objects) > 50000 or time.monotonic() - started > 60:
                    if page.token: collector.CancelRetrievePropertiesEx(page.token)
                    raise InventoryError("Inventory exceeds the configured size or time limit.")
                if not page.token: break
                page = collector.ContinueRetrievePropertiesEx(page.token)
            folders, vms = entities(objects, self.connection)
            return {"connectionId": self.connection, "server": self.host, "version": content.about.version, "vcenterUuid": content.about.instanceUuid, "syncedAt": datetime.now(timezone.utc).isoformat(), "folders": folders, "vms": vms, "scope": "Objects visible to the configured VMware account", "trust": "Certificate fingerprint verified", "state": "connected", "error": None}
        finally:
            if view:
                try: view.Destroy()
                except Exception: pass
            Disconnect(si)

    def save(self, payload):
        with closing(self.store.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT payload->>'vcenterUuid' FROM inventory_snapshots WHERE connection_id=%s", (self.connection,))
                existing=cur.fetchone()
                if existing and existing[0] and existing[0] != payload["vcenterUuid"]:
                    raise InventoryError("vCenter identity changed; review connection configuration.")
                cur.execute("INSERT INTO inventory_snapshots(connection_id,payload,synced_at,last_error) VALUES(%s,%s,%s,NULL) ON CONFLICT(connection_id) DO UPDATE SET payload=excluded.payload,synced_at=excluded.synced_at,last_error=NULL,last_attempt_at=now()", (self.connection, Json(payload), payload["syncedAt"]))
                # Keep history; disappeared means no longer visible, not proven deleted.
                cur.execute("UPDATE inventory_vms SET visible=false WHERE connection_id=%s", (self.connection,))
                for vm in payload["vms"]:
                    cur.execute("INSERT INTO inventory_vms(id,connection_id,moref,instance_uuid,payload) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET moref=excluded.moref,instance_uuid=excluded.instance_uuid,payload=excluded.payload,visible=true,last_seen_at=now()", (vm["id"], self.connection, vm["moref"], vm["instanceUuid"], Json(vm)))

    def load(self):
        with closing(self.store.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT payload FROM inventory_snapshots WHERE connection_id=%s", (self.connection,))
                row = cur.fetchone()
                return row[0] if row else None

    def failure(self, error):
        with closing(self.store.connect()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("UPDATE inventory_snapshots SET last_error=%s,last_attempt_at=now() WHERE connection_id=%s", (error, self.connection))

    async def snapshot(self, refresh=False):
        async with self.lock:
            if self.cache is None:
                try: self.cache = await asyncio.to_thread(self.load)
                except Exception: pass
            if refresh or time.monotonic() - self.last_attempt > 60:
                self.last_attempt = time.monotonic()
                try:
                    payload = await asyncio.to_thread(self.collect)
                    if self.cache and self.cache.get("vcenterUuid") and self.cache["vcenterUuid"] != payload["vcenterUuid"]:
                        raise InventoryError("vCenter identity changed; review connection configuration.")
                    try:
                        await asyncio.to_thread(self.save, payload)
                        payload["persistence"] = "connected"
                    except Exception:
                        payload["persistence"] = "unavailable"
                    self.cache = payload
                except Exception as exc:
                    if isinstance(exc, InventoryError): error = str(exc)
                    elif isinstance(exc, vim.fault.InvalidLogin): error = "VMware authentication failed."
                    elif "thumbprint" in type(exc).__name__.lower() or "thumbprint" in str(exc).lower(): error = "VMware certificate fingerprint mismatch."
                    elif isinstance(exc, vim.fault.NoPermission): error = "VMware inventory permission denied."
                    else: error = "VMware inventory connection failed; check endpoint and certificate trust."
                    self.cache = {**(self.cache or {"connectionId": self.connection, "folders": [], "vms": [], "syncedAt": None, "scope": "Objects visible to the configured VMware account"}), "state": "stale" if self.cache and self.cache.get("syncedAt") else "unavailable", "error": error}
                    try: await asyncio.to_thread(self.failure, error)
                    except Exception: pass
            return self.cache
