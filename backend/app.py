"""Read-only local monitoring boundary for the existing Bareos API."""
import asyncio
from functools import lru_cache
import copy
import re
import ssl
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

import httpx
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.persistence import Store

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 200
SOURCES = {
    "director": "/control/directors/version",
    "jobs": "/configuration/jobs",
    "filesets": "/configuration/filesets",
    "storages": "/configuration/storages",
    "schedules": "/configuration/schedules",
    "sessions": f"/control/jobs?limit={LIMIT}",
    "pools": "/control/pools",
    "volumes": f"/control/volumes?limit={LIMIT}",
}

def number(value):
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0


def timestamp(value):
    if not value or str(value).startswith("0000"):
        return None
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return None


def records(data, key):
    value = data.get(key, {}) if isinstance(data, dict) else {}
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        return [dict(v, name=v.get("name", k)) for k, v in value.items() if isinstance(v, dict)]
    return []


def session(row):
    code = row.get("jobstatus", "?")
    errors = number(row.get("joberrors"))
    status = {"T": "Succeeded", "W": "Warning", "E": "Failed", "e": "Failed", "f": "Failed", "A": "Canceled", "R": "Running", "C": "Created", "B": "Blocked"}.get(code, "Waiting" if code in "FSMsmjcdtpqaiL" else "Unknown")
    if code == "T" and errors:
        status = "Warning"
    return {"id": number(row.get("jobid")), "name": row.get("name", "Unknown job"), "client": row.get("client", ""), "type": {"B": "Backup", "R": "Restore"}.get(row.get("type"), row.get("type", "Unknown")), "level": {"F": "Full", "I": "Incremental", "D": "Differential"}.get(row.get("level"), row.get("level", "")), "status": status, "code": code, "started": timestamp(row.get("starttime")), "ended": timestamp(row.get("endtime")), "duration": row.get("duration", "—"), "bytes": number(row.get("jobbytes")), "files": number(row.get("jobfiles")), "errors": errors, "pool": row.get("poolname", ""), "metadataPruned": str(row.get("purgedfiles")) == "1"}


def volume_records(raw):
    grouped=raw.get("volumes",{})
    rows=[v for group in grouped.values() for v in group] if isinstance(grouped,dict) else grouped
    return [row for row in rows if isinstance(row,dict)] if isinstance(rows,list) else []


def normalize(raw, source_errors):
    sessions = sorted([session(x) for x in records(raw.get("sessions"), "jobs")], key=lambda x: x["id"], reverse=True)
    filesets = {x["name"]: x for x in records(raw.get("filesets"), "filesets")}
    jobs = []
    workloads = []
    for row in records(raw.get("jobs"), "jobs"):
        name = row.get("name", "")
        history = [x for x in sessions if x["name"] == name]
        storage = row.get("storage", [])
        if isinstance(storage, str):
            storage = [storage]
        job = {"name": name, "type": row.get("type", "Unknown"), "client": row.get("client", ""), "fileset": row.get("fileset", ""), "schedule": row.get("schedule") or "Manual", "storage": storage, "pool": row.get("pool", ""), "enabled": bool(row.get("enabled", False)), "level": row.get("level", ""), "latest": history[0] if history else None}
        jobs.append(job)
        plugin = " ".join(str(v) for inc in filesets.get(job["fileset"], {}).get("include", []) for v in inc.get("plugin", []))
        if "bareos-fd-vmware" not in plugin:
            continue
        vm = re.search(r"(?:^|:)vmname=([^:]+)", plugin)
        dc = re.search(r"(?:^|:)dc=([^:]+)", plugin)
        uuid = re.search(r"(?:^|:)uuid=([^:]+)", plugin)
        folder = re.search(r"(?:^|:)folder=([^:]+)", plugin)
        backups = [x for x in history if x["type"] == "Backup" and x["status"] in ("Succeeded", "Warning")]
        good = [x for x in backups if x["status"] == "Succeeded"]
        evidence = "Unknown" if "sessions" in source_errors else ("Backup recorded" if good else ("Warning" if backups else "No backup recorded"))
        workloads.append({"name": vm.group(1) if vm else (name.removeprefix("VMware-") if uuid else name), "job": name, "folder": folder.group(1) if folder else "Unknown", "datacenter": dc.group(1) if dc else None, "instanceUuid": uuid.group(1) if uuid else None, "proxy": job["client"], "storage": storage, "schedule": job["schedule"], "evidence": evidence, "latestBackup": good[0] if good else (backups[0] if backups else None), "sessions": history[:12], "backupCount": len(backups), "identityVerified": False, "restoreVerified": False})
    storages = [{"name": x.get("name", ""), "address": x.get("address", ""), "port": number(x.get("port")), "devices": x.get("device", []), "mediaType": x.get("mediatype", ""), "enabled": bool(x.get("enabled")), "concurrency": number(x.get("maximumconcurrentjobs"))} for x in records(raw.get("storages"), "storages")]
    schedules = [{"name": x.get("name", ""), "enabled": bool(x.get("enabled")), "rules": x.get("run", [])} for x in records(raw.get("schedules"), "schedules")]
    pools = [{"name": x.get("name", ""), "volumes": number(x.get("numvols")), "maxVolumes": number(x.get("maxvols")), "retentionDays": number(x.get("volretention")) // 86400} for x in records(raw.get("pools"), "pools")]
    volume_raw = raw.get("volumes", {}).get("volumes", {})
    volume_rows = [v for vs in volume_raw.values() for v in vs] if isinstance(volume_raw, dict) else volume_raw
    volumes = [{"name": x.get("volumename", ""), "pool": x.get("pool", ""), "storage": x.get("storage", ""), "status": x.get("volstatus", "Unknown"), "bytes": number(x.get("volbytes"))} for x in volume_rows if isinstance(x, dict)] if isinstance(volume_rows, list) else []
    director = raw.get("director", {})
    return {"director": {"name": director.get("name", "Unknown"), "version": director.get("version", "Unknown")}, "jobs": sorted(jobs, key=lambda x: x["name"]), "workloads": sorted(workloads, key=lambda x: x["name"]), "sessions": sessions, "storages": storages, "pools": pools, "volumes": volumes, "schedules": schedules, "sessionTotal": number(raw.get("sessions", {}).get("totalItems")), "sessionLimit": LIMIT, "capabilities": {"readOnly": True, "vmwareInventory": False, "provisioning": False, "restore": False}}


class Gateway:
    def __init__(self):
        self.values = dotenv_values(ROOT / ".env")
        self.base = (self.values.get("BAREOS_API_BASE_URL") or "").rstrip("/")
        self.context = ssl.create_default_context()
        pem = self.values.get("BAREOS_API_TLS_CA_PEM")
        if pem:
            self.context.load_verify_locations(cadata=pem)
        self.token = None
        self.operation_dispatch_enabled = str(dotenv_values(ROOT/".env").get("BACKUPCENTER_OPERATION_DISPATCH_ENABLED", "0"))=="1"
        default_jobs = ",".join("VMware-" + vm for vm in ("MTIMRWZTNA01", "MTIMRWPGSQL01", "MTIMRWNTP02", "MTIMRWNTP01", "MTIMRWKF01", "MTIMRWCNTDEV"))
        self.onboarding_vm_uuids = frozenset(x.strip() for x in self.values.get("BACKUPCENTER_ONBOARDING_UUIDS", "").split(",") if x.strip()) if self.values.get("BACKUPCENTER_ONBOARDING_ENABLED")=="1" else frozenset()
        self.operation_jobs = frozenset(name.strip() for name in self.values.get("BACKUPCENTER_OPERATION_JOBS", default_jobs).split(",") if name.strip())
        self.restore_enabled = str(dotenv_values(ROOT/".env").get("BACKUPCENTER_RESTORE_DISPATCH_ENABLED", "0"))=="1"
        self.restore_test_job = dotenv_values(ROOT/".env").get("BACKUPCENTER_RESTORE_TEST_JOB", "")
        self.lock = asyncio.Lock()
        self.cached = None
        self.cached_at = float("-inf")
        self.store = Store()
        self.restored_cache = False
        self.persistence = {"state": "not-configured" if not self.store.configured else "initializing"}

    def redact(self, text):
        for key, value in self.values.items():
            if value and any(x in key.upper() for x in ("PASSWORD", "SECRET", "VCPASS")):
                text = text.replace(value, "[redacted]")
        return re.sub(r'(?i)((?:password|vcpass|token|secret|authorization)\s*[=:]\s*)[^\s,;]+', r'\1[redacted]', text)

    async def authenticate(self, client):
        if not self.base.startswith("https://"):
            raise ValueError("HTTPS required")
        endpoint = self.values.get("BAREOS_API_TOKEN_ENDPOINT") or "/token"
        url = endpoint if endpoint.startswith("https://") else self.base + "/" + endpoint.lstrip("/")
        if urlparse(url).netloc != urlparse(self.base).netloc:
            raise ValueError("Token endpoint must use the API origin")
        response = await client.post(url, data={"username": self.values.get("BAREOS_API_USERNAME", ""), "password": self.values.get("BAREOS_API_PASSWORD", "")})
        response.raise_for_status()
        self.token = response.json()["access_token"]

    async def get(self, client, path, query=None):
        if self.token is None:
            await self.authenticate(client)
        response = await client.request("GET",self.base + path, headers={"Authorization": "Bearer " + self.token}, **({"json":query} if query is not None else {}))
        if response.status_code == 401:
            await self.authenticate(client)
            response = await client.request("GET",self.base + path, headers={"Authorization": "Bearer " + self.token}, **({"json":query} if query is not None else {}))
        response.raise_for_status()
        return response.json()

    @staticmethod
    def error(exc):
        if isinstance(exc, httpx.HTTPStatusError):
            return f"Bareos API returned HTTP {exc.response.status_code}."
        if isinstance(exc, httpx.TimeoutException):
            return "Bareos API timed out. Check the network and retry."
        return "Cannot read the Bareos API. Check connection settings and certificate trust."

    async def snapshot(self, force=False):
        async with self.lock:
            if not self.restored_cache:
                self.restored_cache = True
                if self.store.configured:
                    try:
                        self.cached = await asyncio.to_thread(self.store.load)
                        self.persistence = await asyncio.to_thread(self.store.status)
                    except Exception:
                        self.persistence = {"state": "unavailable", "message": "PostgreSQL unavailable; live monitoring continues without persistence."}
            if self.cached and not force and time.monotonic() - self.cached_at < 15:
                return copy.deepcopy(self.cached)
            raw, errors = {}, {}
            async with httpx.AsyncClient(verify=self.context, timeout=12, trust_env=False) as client:
                for key, path in SOURCES.items():
                    try:
                        value = await self.get(client, path)
                        if not isinstance(value, dict):
                            raise ValueError("Unexpected API response")
                        if key == "sessions" and number(value.get("totalItems")) > LIMIT:
                            total = number(value["totalItems"])
                            value = await self.get(client, f"/control/jobs?limit={LIMIT}&offset={total - LIMIT}")
                            value["totalItems"] = total
                        raw[key] = value
                    except Exception as exc:
                        errors[key] = self.error(exc)
                        # Authentication/network failure affects every endpoint; avoid repeated timeouts.
                        if key == "director":
                            errors = {k: errors[key] for k in SOURCES}
                            break
            if len(errors) == len(SOURCES):
                if self.cached:
                    value = copy.deepcopy(self.cached)
                    value.update(connection="stale", sourceErrors=errors, persistence=self.persistence)
                    value["capabilities"] = dict(value.get("capabilities",{}), controls=False, readOnly=True)
                    return value
                raise HTTPException(502, detail="Unable to connect to Bareos. Check API credentials, network, and TLS trust.")
            value = normalize(raw, errors)
            value.update(connection="partial" if errors else "connected", syncedAt=datetime.now(timezone.utc).isoformat(), sourceErrors=errors)
            if self.store.configured:
                try:
                    await asyncio.to_thread(self.store.save, value)
                    self.persistence = await asyncio.to_thread(self.store.status)
                except Exception:
                    self.persistence = {"state": "unavailable", "message": "PostgreSQL unavailable; this snapshot is not confirmed durable."}
            value["capabilities"]["controls"] = self.operation_dispatch_enabled and self.persistence.get("state")=="connected" and "jobs" not in errors and "director" not in errors
            value["capabilities"]["readOnly"] = not value["capabilities"]["controls"]
            value["persistence"] = self.persistence
            self.cached, self.cached_at = value, time.monotonic()
            return copy.deepcopy(value)


@asynccontextmanager
async def lifespan(app):
    from backend.operations import worker
    task=asyncio.create_task(worker(gateway))
    yield
    task.cancel()
    try:await task
    except asyncio.CancelledError:pass

app = FastAPI(title="Backup Center API", docs_url=None, redoc_url=None, lifespan=lifespan)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def sanitized_validation(request,exc):
    return JSONResponse({"detail":[{"loc":e["loc"],"msg":e["msg"],"type":e["type"]} for e in exc.errors()]},status_code=422)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
_gateway = None

def gateway():
    global _gateway
    if _gateway is None:
        try:
            _gateway = Gateway()
        except Exception:
            raise HTTPException(503, "Invalid backend settings or trust certificate.")
    return _gateway

@app.middleware("http")
async def operational_boundary(request, call_next):
    from fastapi.responses import JSONResponse
    from backend import auth
    allowed_posts={"/api/operations","/api/auth/login","/api/auth/logout","/api/auth/password","/api/users","/api/provisioning/preview","/api/provisioning/apply","/api/recovery/vmware/plan","/api/recovery/vmware/restore","/api/policies"}
    mutation=request.method=="POST" and (request.url.path in allowed_posts or request.url.path.startswith("/api/users/") or (request.url.path.startswith("/api/alerts/") and request.url.path.endswith("/ack")))
    if request.method not in ("GET", "HEAD") and not mutation:
        return JSONResponse({"detail": "This operation is not enabled."}, status_code=405)
    if mutation and (request.headers.get("origin") not in ("http://127.0.0.1:3000", "http://localhost:3000") or request.headers.get("x-backup-center-action")!="confirmed"):
        return JSONResponse({"detail":"A confirmed same-origin operation is required."},status_code=403)
    if request.url.path not in ("/api/health","/api/auth/login"):
        try: user=await asyncio.to_thread(auth.session_user,request.cookies.get(auth.COOKIE))
        except Exception:return JSONResponse({"detail":"Identity database unavailable."},status_code=503)
        if not user:return JSONResponse({"detail":"Sign in to continue."},status_code=401)
        request.state.user=user
        if (request.url.path=="/api/users" or request.url.path.startswith("/api/users/")) and user["role"]!="Admin":
            return JSONResponse({"detail":"Administrator permission required."},status_code=403)
        if (request.url.path in ("/api/provisioning/preview","/api/provisioning/apply","/api/recovery/vmware/plan","/api/recovery/vmware/restore","/api/policies") or request.url.path.startswith("/api/alerts/")) and mutation and user["role"]!="Admin":
            return JSONResponse({"detail":"Administrator permission required."},status_code=403)
        if request.url.path=="/api/operations" and mutation and user["role"] not in ("Admin","Backup Operator"):
            return JSONResponse({"detail":"Backup operation permission required."},status_code=403)
    origin = request.headers.get("origin")
    if origin and origin not in ("http://127.0.0.1:3000", "http://localhost:3000"):
        return JSONResponse({"detail": "Origin not allowed."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.get("/api/health")
def health():
    return {"service":"backup-center","authentication":"local-accounts","binding":"loopback-only","controls":["run","cancel"],"restore":"gated; acceptance pending"}

@app.get("/api/snapshot")
async def snapshot(request: Request, refresh: bool = False):
    result=copy.deepcopy(await gateway().snapshot(refresh))
    result["capabilities"]["controls"]=bool(result["capabilities"].get("controls") and request.state.user["role"] in ("Admin","Backup Operator"))
    result["capabilities"]["readOnly"]=not result["capabilities"]["controls"]
    result["capabilities"]["operationJobs"]=sorted(getattr(gateway(),"operation_jobs",[]))
    result["capabilities"]["onboardingUuids"]=sorted(getattr(gateway(),"onboarding_vm_uuids",())) if request.state.user["role"]=="Admin" else []
    result["capabilities"]["vmwareInventory"]=True
    result["capabilities"]["provisioningPreview"]=request.state.user["role"]=="Admin"
    result["capabilities"]["provisioningApply"]=request.state.user["role"]=="Admin" and result.get("persistence",{}).get("state")=="connected"
    return result

@app.get("/api/sessions/{job_id}/logs")
async def logs(job_id: int):
    if job_id < 1:
        raise HTTPException(422, "Invalid JobId.")
    g = gateway()
    async with g.lock:
        try:
            async with httpx.AsyncClient(verify=g.context, timeout=15, trust_env=False) as client:
                data = await g.get(client, f"/control/jobs/logs/{job_id}")
            return {"jobId": job_id, "lines": [{"time": timestamp(x.get("time")), "text": g.redact(str(x.get("logtext", "")))[:8000]} for x in records(data, "joblog")[:2000]], "limit": 2000}
        except Exception as exc:
            raise HTTPException(502, g.error(exc))


@app.get("/api/audit")
async def audit():
    store = gateway().store
    if not store.configured:
        raise HTTPException(503, "Application database not configured.")
    try:
        return {"events": await asyncio.to_thread(store.audit), "limit": 100}
    except Exception:
        raise HTTPException(503, "Application audit database unavailable.")


class OperationRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind: Literal["run","cancel","restore"]
    target: str = Field(min_length=1,max_length=128)
    idempotency_key: UUID
    confirmed: Literal[True]

    @model_validator(mode="after")
    def canonical_target(self):
        if self.kind in ("cancel","restore"):
            if not self.target.isdigit() or not (0<int(self.target)<=9223372036854775807):
                raise ValueError("A positive backup JobId is required.")
            self.target=str(int(self.target))
        return self


@app.post("/api/operations",status_code=202)
async def create_operation(body: OperationRequest, request: Request):
    g=gateway()
    if body.kind=="restore" and request.state.user["role"]!="Admin":raise HTTPException(403,"Isolated restore currently requires Admin permission.")
    if not g.store.configured:raise HTTPException(503,"Operation journal is unavailable; no command was sent.")
    try:
        # Check duplicate key before changing eligibility (a completed operation remains replay-safe).
        match=await asyncio.to_thread(g.store.operation_key,body.idempotency_key)
        if match:
            if match["actor"]!=request.state.user["username"]:raise HTTPException(409,"Request key belongs to another operator.")
            if match["kind"]!=body.kind or match["target"]!=body.target:raise HTTPException(409,"Idempotency key belongs to another request.")
            return match
        from backend.operations import validate
        async with g.lock:
            async with httpx.AsyncClient(verify=g.context,timeout=12,trust_env=False) as client:
                await validate(g,client,body.kind,body.target)
        return await asyncio.to_thread(g.store.prepare,body.kind,body.target,body.idempotency_key,request.state.user["username"])
    except HTTPException:raise
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(503,"Preflight or journal unavailable; no command was queued.")


@app.get("/api/operations")
async def operations(key: UUID = None):
    try:
        if key:
            row=await asyncio.to_thread(gateway().store.operation_key,key)
            return {"operations":[row] if row else [],"limit":1}
        return {"operations":await asyncio.to_thread(gateway().store.operations),"limit":100}
    except Exception:raise HTTPException(503,"Operation journal unavailable.")


@app.get("/api/operations/{operation_id}")
async def operation(operation_id: UUID):
    try:row=await asyncio.to_thread(gateway().store.operation,operation_id)
    except Exception:raise HTTPException(503,"Operation journal unavailable.")
    if not row:raise HTTPException(404,"Operation not found.")
    return row


@lru_cache(maxsize=1)
def inventory():
    from backend.inventory import Inventory
    return Inventory(gateway().store)


@app.get("/api/inventory")
async def inventory_list(q: str = "", folder: str = "", page: int = 1, refresh: bool = False, descending: bool = False):
    if page < 1 or page > 100000 or len(q) > 200 or len(folder) > 128:
        raise HTTPException(422, "Invalid inventory filters.")
    from backend.inventory import reconcile
    source = await inventory().snapshot(refresh)
    bareos = await gateway().snapshot()
    assignments = {}
    try:
        if gateway().store.configured:
            assignments = await asyncio.to_thread(gateway().store.assignment_map)
    except Exception:
        assignments = {}
    rows = reconcile(source["vms"], bareos.get("workloads", []), assignments)
    rows = sorted([r for r in rows if (not folder or folder in r["ancestorIds"]) and q.casefold() in (r["name"] + " " + r["folder"] + " " + (r["host"] or "")).casefold()], key=lambda r: (r["name"].casefold(), r["id"]), reverse=descending)
    total = len(rows)
    pages = max(1, (total + 24) // 25)
    page = min(page, pages)
    return {**{k: v for k, v in source.items() if k != "vms"}, "vms": rows[(page-1)*25:page*25], "total": total, "totalVisible": len(source["vms"]), "page": page, "pages": pages, "pageSize": 25, "bareosState": bareos.get("connection"), "provisioning": False}


class LoginRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    username: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    password: str = Field(min_length=1,max_length=256)


@app.post("/api/auth/login")
async def sign_in(body: LoginRequest,response: Response):
    from backend import auth
    try: user=await asyncio.to_thread(auth.login,body.username,body.password)
    except Exception:raise HTTPException(503,"Identity database unavailable.")
    if not user:raise HTTPException(401,"Sign-in failed. Check your credentials; repeated failures pause sign-in for 15 minutes.")
    response.set_cookie(auth.COOKIE,user.pop("token"),max_age=28800,httponly=True,samesite="strict",secure=False,path="/")
    return user


@app.get("/api/auth/me")
async def identity(request: Request):return request.state.user


@app.post("/api/auth/logout")
async def sign_out(request: Request,response: Response):
    from backend import auth
    await asyncio.to_thread(auth.logout,request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE,path="/")
    return {"message":"Signed out."}


class PasswordRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    current: str = Field(min_length=1,max_length=256)
    password: str = Field(min_length=14,max_length=256)


@app.post("/api/auth/password")
async def password_change(body: PasswordRequest,request: Request,response: Response):
    from backend import auth
    try:await asyncio.to_thread(auth.change_password,request.state.user["username"],body.current,body.password)
    except ValueError as exc:raise HTTPException(409,str(exc))
    response.delete_cookie(auth.COOKIE,path="/")
    return {"message":"Password changed. Sign in again."}


class CreateUserRequest(LoginRequest):
    password: str = Field(min_length=14,max_length=256)
    role: Literal["Admin","Backup Operator","Viewer"]
    confirmed: Literal[True]


@app.get("/api/users")
async def user_list():
    from backend.auth import users
    return {"users":await asyncio.to_thread(users),"limit":200}


@app.post("/api/users",status_code=201)
async def user_create(body: CreateUserRequest,request: Request):
    from backend.auth import create_user
    try:await asyncio.to_thread(create_user,body.username,body.password,body.role,request.state.user["username"])
    except ValueError as exc:raise HTTPException(409,str(exc))
    except PermissionError:raise HTTPException(403,"Administrator permission was revoked.")
    return {"username":body.username,"role":body.role}


class ChangeUserRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    role: Literal["Admin","Backup Operator","Viewer"]
    enabled: bool
    confirmed: Literal[True]


@app.post("/api/users/{username}")
async def user_change(username: str,body: ChangeUserRequest,request: Request):
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,63}",username):raise HTTPException(422,"Invalid username.")
    from backend.auth import change_user
    try:await asyncio.to_thread(change_user,username,body.role,body.enabled,request.state.user["username"])
    except ValueError as exc:raise HTTPException(409,str(exc))
    except PermissionError:raise HTTPException(403,"Administrator permission was revoked.")
    return {"username":username,"role":body.role,"enabled":body.enabled}


@app.get("/api/recovery/{job_id}")
async def recovery_inspection(job_id: int):
    if job_id<1 or job_id>9223372036854775807:raise HTTPException(422,"Invalid backup JobId.")
    g=gateway()
    async with g.lock:
        try:
            async with httpx.AsyncClient(verify=g.context,timeout=30,trust_env=False) as client:
                row=await g.get(client,"/control/jobs/"+str(job_id))
                if row.get("type")!="B" or row.get("jobstatus") not in ("T","W"):raise HTTPException(409,"Select a completed backup session.")
                jobs=await g.get(client,"/configuration/jobs")
                definition=jobs.get("jobs",{}).get(row.get("name"),{})
                filesets=await g.get(client,"/configuration/filesets")
                definition_fs=filesets.get("filesets",{}).get(definition.get("fileset"),{})
                plugin=" ".join(str(v) for inc in definition_fs.get("include",[]) for v in inc.get("plugin",[]))
                if "bareos-fd-vmware" not in plugin:raise HTTPException(409,"This inspection supports configured VMware plugin backups only.")
                chain=await g.get(client,"/backupcenter/recovery/"+str(job_id))
                files=await g.get(client,"/control/jobs/files/"+str(job_id))
                media=await g.get(client,"/control/volumes?limit=1000")
                volumes=[{"name":v.get("volumename"),"status":v.get("volstatus")} for v in volume_records(media)]
            from backend.recovery import normalize_recovery
            result=normalize_recovery(chain,files,volumes)
            result["dispatchEnabled"]=bool(g.operation_dispatch_enabled and g.restore_enabled and row.get("name")==g.restore_test_job and not result["blockers"])
            result["modes"][0]["state"]="Isolated export implemented; live acceptance pending"
            result["restoreTests"]=[]
            try:
                attempts=await asyncio.to_thread(g.store.operations)
                for attempt in [a for a in attempts if a["kind"]=="restore" and a["target"]==str(job_id) and a["parameters"].get("mode")=="vmware-new-vm" and a["state"]=="Completed"][:3]:
                    from backend.direct_restore_target import invoke
                    try:
                        proof=await asyncio.to_thread(invoke,{"action":"status","request_id":str(attempt["idempotency_key"])})
                        result["restoreTests"].append({"operationId":str(attempt["id"]),"restoreJobId":attempt["job_id"],"vmName":proof["destination"]["vm_name"],"execution":attempt["parameters"].get("sessionStatus","Completed"),"isolationVerified":proof.get("isolationVerified",False),"bootVerified":proof.get("bootVerification",{}).get("bootVerified",False),"finalPower":proof.get("bootVerification",{}).get("finalPower",proof.get("power","Unknown"))})
                    except Exception:result["restoreTestEvidenceUnavailable"]=True
            except Exception:result["restoreTestEvidenceUnavailable"]=True
            return result
        except HTTPException:raise
        except Exception:raise HTTPException(502,"Recovery inspection unavailable. Check Director access and the typed recovery gateway extension.")


class ProvisioningPreviewRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    vm_ids: list[UUID] = Field(min_length=1,max_length=25)
    storage: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    policy_id: Optional[UUID] = None
    policy_revision: int = Field(default=0,ge=0)


class ProvisioningApplyRequest(ProvisioningPreviewRequest):
    idempotency_key: UUID
    confirmed: Literal[True]


@app.post("/api/provisioning/preview")
async def provisioning_preview(body: ProvisioningPreviewRequest):
    from backend.inventory import reconcile
    from backend.provisioning import preview
    source=await inventory().snapshot(True)
    if source["state"]!="connected" or source.get("persistence")!="connected":raise HTTPException(409,"Fresh persisted inventory is required.")
    bareos=await gateway().snapshot(True)
    if bareos["connection"]!="connected" or bareos["sourceErrors"]:raise HTTPException(409,"Complete current Bareos configuration is required.")
    ids={str(x) for x in body.vm_ids}
    rows=[v for v in reconcile(source["vms"],bareos["workloads"]) if v["id"] in ids]
    if len(rows)!=len(ids):raise HTTPException(409,"Selected VM is no longer visible. Refresh the selection.")
    storage=next((s for s in bareos["storages"] if s["name"]==body.storage),None)
    if not storage:raise HTTPException(409,"Storage resource is no longer available.")
    policy=None
    if body.policy_id:
        policy=next((p for p in await asyncio.to_thread(gateway().store.policies) if str(p['id'])==str(body.policy_id)),None)
        if not policy or policy['state']!='Draft' or policy['revision']!=body.policy_revision:raise HTTPException(409,"Policy revision changed. Reload the current policy before previewing.")
        if policy['definition']['storage']!=body.storage:raise HTTPException(409,"Selected storage does not match this draft policy.")
    try:result=preview(rows,storage,policy,[w.get("job") for w in bareos.get("workloads",[])],live_uuids=getattr(gateway(),"onboarding_vm_uuids",()))
    except ValueError as exc:raise HTTPException(409,str(exc))
    current={x["name"] for x in bareos["jobs"]}
    if any(c["job"] in current for c in result["changes"]):raise HTTPException(409,"Generated job already exists; review assignment.")
    return result


@app.post("/api/provisioning/apply",status_code=202)
async def provisioning_apply(body: ProvisioningApplyRequest, request: Request):
    if not gateway().store.configured:raise HTTPException(503,"Provisioning journal is unavailable; no rehearsal was queued.")
    match=await asyncio.to_thread(gateway().store.operation_key,body.idempotency_key)
    if match:
        if match["actor"]!=request.state.user["username"]:raise HTTPException(409,"Request key belongs to another operator.")
        if match["kind"]!="provision":raise HTTPException(409,"Idempotency key belongs to another request.")
        return match
    plan=await provisioning_preview(ProvisioningPreviewRequest(vm_ids=body.vm_ids,storage=body.storage,policy_id=body.policy_id,policy_revision=body.policy_revision))
    try:return await asyncio.to_thread(gateway().store.prepare_provisioning,body.idempotency_key,request.state.user["username"],plan)
    except PermissionError:raise HTTPException(403,"Administrator permission was revoked.")
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(503,"Provisioning rehearsal could not be staged. Reload current inventory and retry.")


@app.get("/api/reports/backup-sessions")
async def backup_report(date_from:date,date_to:date,format:Literal["json","csv"]="json"):
    from backend.reports import period,csv_report
    try:period(date_from,date_to)
    except ValueError as exc:raise HTTPException(422,str(exc))
    try:result=await asyncio.to_thread(gateway().store.report,date_from,date_to)
    except Exception:raise HTTPException(503,"Observed-session report database unavailable.")
    if format=="csv":return Response(csv_report(result),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=backup-sessions-"+date_from.isoformat()+"-"+date_to.isoformat()+".csv"})
    return result


class PolicyRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    id: Optional[UUID] = None
    expected_revision: int = Field(default=0,ge=0)
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{2,79}$")
    storage: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    freshness_hours: int = Field(ge=1,le=720)
    retention_days: int = Field(ge=1,le=3650)
    maximum_volumes: int = Field(ge=2,le=1000)
    schedule: Literal["Manual","Daily"]
    time_wita: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def consistent(self):
        if self.id and self.expected_revision<1:raise ValueError("An existing policy requires its current revision.")
        if not self.id and self.expected_revision!=0:raise ValueError("New policies start at revision zero.")
        if self.schedule=="Daily" and self.freshness_hours<24:raise ValueError("Daily schedules require a freshness target of at least 24 hours.")
        return self


@app.get("/api/policies")
async def policies():
    try:return {"policies":await asyncio.to_thread(gateway().store.policies),"limit":100}
    except Exception:raise HTTPException(503,"Policy database unavailable.")


@app.post("/api/policies")
async def policy_save(body: PolicyRequest,request: Request):
    current=await gateway().snapshot(True)
    if current["connection"]!="connected" or "storages" in current["sourceErrors"]:raise HTTPException(409,"Current storage configuration is required.")
    if not any(s["name"]==body.storage and s["mediaType"]=="SMBFile" and s["enabled"] for s in current["storages"]):raise HTTPException(409,"Select an enabled shared SMBFile storage resource.")
    try:return await asyncio.to_thread(gateway().store.save_policy,body.model_dump(),request.state.user["username"])
    except PermissionError:raise HTTPException(403,"Administrator permission was revoked.")
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(503,"Policy save failed; reload the policy list before retrying.")


@app.get("/api/alerts")
async def alerts():
    try:
        source=await gateway().snapshot()
        rows=await asyncio.to_thread(gateway().store.alerts)
        state="current" if source.get('persistence',{}).get('state')=='connected' and source['connection'] in ('connected','partial') and not any(k in source['sourceErrors'] for k in ('jobs','sessions')) else "stale"
        return {"alerts":rows,"limit":100,"evaluationState":state,"syncedAt":source['syncedAt'],"scope":"Latest observed terminal sessions for currently configured Backup jobs; no RPO or recovery verification."}
    except Exception:raise HTTPException(503,"Alert journal unavailable.")


class AcknowledgeRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    revision:int=Field(ge=1)


@app.post("/api/alerts/{alert_id}/ack")
async def alert_acknowledge(alert_id:UUID,body:AcknowledgeRequest,request:Request):
    try:return await asyncio.to_thread(gateway().store.acknowledge,alert_id,body.revision,request.state.user['username'])
    except PermissionError:raise HTTPException(403,"Administrator permission was revoked.")
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(503,"Alert acknowledgement unavailable. Reload current state before retrying.")


from backend.vm_restore import VMRestoreDestination,build_vm_restore_plan
class VMRestorePlanRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    source_job_id:int=Field(gt=0,le=9223372036854775807)
    destination:VMRestoreDestination

@app.post("/api/recovery/vmware/plan")
async def vm_restore_plan(body:VMRestorePlanRequest,request:Request):
    if request.state.user["role"]!="Admin":raise HTTPException(403,"Administrator permission required.")
    evidence=await recovery_inspection(body.source_job_id)
    g=gateway()
    try:
        async with g.lock:
            async with httpx.AsyncClient(verify=g.context,timeout=30,trust_env=False) as client:
                row=await g.get(client,"/control/jobs/"+str(body.source_job_id))
                jobs=await g.get(client,"/configuration/jobs")
                definition=jobs.get("jobs",{}).get(row.get("name"),{})
                sets=await g.get(client,"/configuration/filesets")
                fs=sets.get("filesets",{}).get(definition.get("fileset"),{})
                plugin=" ".join(str(v) for inc in fs.get("include",[]) for v in inc.get("plugin",[]))
        if getattr(g,"values",{}).get("BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED")=="1":
            if evidence["blockers"]:raise ValueError("Resolve recovery blockers before selecting a VMware target.")
            from backend.direct_restore_target import invoke
            return await asyncio.to_thread(invoke,{"action":"plan","job_id":body.source_job_id,"destination":body.destination.model_dump()})
        return build_vm_restore_plan(evidence,body.destination,plugin)
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(502,"VMware restore review unavailable. Check source configuration and try again.")


@app.get("/api/recovery/vmware/targets")
async def vm_restore_targets(request:Request):
    if request.state.user["role"]!="Admin":raise HTTPException(403,"Administrator permission required.")
    if gateway().values.get("BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED")!="1":raise HTTPException(409,"Direct VMware restore is disabled.")
    try:
        from backend.direct_restore_target import invoke
        return await asyncio.to_thread(invoke,{"action":"targets"})
    except Exception:raise HTTPException(502,"VMware destination inventory unavailable. Check pinned connection and permissions.")

class VMRestoreSubmitRequest(VMRestorePlanRequest):
    idempotency_key:UUID
    review_digest:str=Field(pattern=r"^[0-9a-f]{64}$")
    confirmed:Literal[True]

@app.post("/api/recovery/vmware/restore",status_code=202)
async def vm_restore_submit(body:VMRestoreSubmitRequest,request:Request):
    if request.state.user["role"]!="Admin":raise HTTPException(403,"Administrator permission required.")
    g=gateway()
    if not g.operation_dispatch_enabled or g.values.get("BACKUPCENTER_DIRECT_VM_RESTORE_ENABLED")!="1":raise HTTPException(409,"Direct VMware restore is disabled.")
    parameters={"mode":"vmware-new-vm","destination":body.destination.model_dump(),"reviewDigest":body.review_digest,"summary":body.destination.vm_name+" → "+body.destination.host+" / "+body.destination.datastore}
    try:
        existing=await asyncio.to_thread(g.store.operation_key,body.idempotency_key)
        if existing:
            if existing["actor"]!=request.state.user["username"] or existing["kind"]!="restore" or existing["target"]!=str(body.source_job_id) or any(existing["parameters"].get(k)!=v for k,v in parameters.items()):raise HTTPException(409,"Request key belongs to a different restore intent.")
            return existing
        plan=await vm_restore_plan(body,request)
        if not plan.get("dispatchEnabled") or plan["reviewDigest"]!=body.review_digest:raise HTTPException(409,"Restore destination/source changed. Review again.")
        return await asyncio.to_thread(g.store.prepare,"restore",str(body.source_job_id),body.idempotency_key,request.state.user["username"],parameters)
    except HTTPException:raise
    except ValueError as exc:raise HTTPException(409,str(exc))
    except Exception:raise HTTPException(503,"Restore journal unavailable; no request queued.")


@app.get("/api/recovery/vmware/result/{operation_id}")
async def vm_restore_result(operation_id:UUID,request:Request):
    if request.state.user["role"]!="Admin":raise HTTPException(403,"Administrator permission required.")
    try:
        row=await asyncio.to_thread(gateway().store.operation,operation_id)
        if not row or row["kind"]!="restore" or row["parameters"].get("mode")!="vmware-new-vm":raise HTTPException(404,"Direct VMware restore operation not found.")
        from backend.direct_restore_target import invoke
        return await asyncio.to_thread(invoke,{"action":"status","request_id":str(row["idempotency_key"])})
    except HTTPException:raise
    except Exception:raise HTTPException(502,"Restore verification receipt unavailable. Check operation and server history.")


@app.get("/api/sessions/{job_id}/progress")
async def session_progress(job_id:int):
    if not 0<job_id<2**63:raise HTTPException(422,"Invalid JobId.")
    g=gateway()
    async with g.lock:
        try:
            async with httpx.AsyncClient(verify=g.context,timeout=15,trust_env=False) as client:
                row=await g.get(client,"/control/jobs/"+str(job_id))
                if row.get("type")!="R":raise HTTPException(409,"Select a restore session.")
                data=await g.get(client,"/control/jobs/logs/"+str(job_id))
            lines=[{"time":timestamp(x.get("time")),"text":g.redact(str(x.get("logtext","")))[:8000]} for x in records(data,"joblog")[-2000:]]
            from backend.session_progress import progress
            return progress(row,lines)
        except HTTPException:raise
        except Exception:raise HTTPException(502,"Live restore progress unavailable. Last displayed values may be stale.")
