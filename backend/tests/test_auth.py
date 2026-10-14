from uuid import uuid4
from fastapi.testclient import TestClient
from backend import app as module, auth
from backend.tests.test_operations import HEADERS, FakeGateway
from backend.operations import dispatch
import asyncio


def test_password_hash_is_salted_and_correct():
    password="test-only-long-password"
    a=auth.password_hash(password)
    b=auth.password_hash(password)
    assert a!=b and password not in a
    assert auth.verify_password(password,a)
    assert not auth.verify_password("wrong",a)
    assert not auth.verify_password(password,"malformed")


def test_anonymous_and_expired_sessions_cannot_read_or_mutate(monkeypatch):
    monkeypatch.setattr(auth,"session_user",lambda token:None)
    with TestClient(module.app) as client:
        for path in ("/api/snapshot","/api/inventory","/api/audit","/api/operations","/api/users"):
            assert client.get(path).status_code==401
        assert client.post("/api/operations",headers=HEADERS,json={}).status_code==401


def test_viewer_cannot_call_operation_or_identity_routes(monkeypatch):
    monkeypatch.setattr(auth,"session_user",lambda token:{"username":"viewer","role":"Viewer"})
    with TestClient(module.app) as client:
        assert client.post("/api/operations",headers=HEADERS,json={}).status_code==403
        assert client.get("/api/users").status_code==403
        assert client.post("/api/users",headers=HEADERS,json={}).status_code==403


def test_identity_database_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(auth,"session_user",lambda token:(_ for _ in ()).throw(RuntimeError("offline")))
    with TestClient(module.app) as client:
        assert client.get("/api/snapshot").status_code==503
        assert client.post("/api/operations",headers=HEADERS,json={}).status_code==503


def test_login_cookie_is_http_only_and_csrf_is_required(monkeypatch):
    monkeypatch.setattr(auth,"login",lambda username,password:{"username":username,"role":"Viewer","token":"test-only-token"})
    with TestClient(module.app) as client:
        body={"username":"viewer","password":"test"}
        assert client.post("/api/auth/login",json=body).status_code==403
        response=client.post("/api/auth/login",headers=HEADERS,json=body)
        assert response.status_code==200 and "token" not in response.json()
        cookie=response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=28800" in cookie


def test_permission_revocation_prevents_worker_dispatch():
    async def run():
        g=FakeGateway()
        g.store.actor_allowed=lambda actor,kind:False
        op=g.store.prepare("run","VMware-safe",uuid4())
        await dispatch(g,op)
        assert g.store.rows[op["id"]]["state"]=="Failed"
        assert g.store.transitions==["Failed"]
    asyncio.run(run())



def test_validation_does_not_echo_passwords(monkeypatch):
    with TestClient(module.app) as client:
        response=client.post("/api/users",headers=HEADERS,json={"username":"test","password":"secret","role":"Viewer","confirmed":True})
        assert response.status_code==422 and "secret" not in response.text


def test_viewer_cannot_change_another_users_permissions(monkeypatch):
    monkeypatch.setattr(auth,"session_user",lambda token:{"username":"viewer","role":"Viewer"})
    with TestClient(module.app) as client:
        assert client.post("/api/users/admin",headers=HEADERS,json={"role":"Viewer","enabled":False,"confirmed":True}).status_code==403



def test_operator_can_read_identity_but_cannot_manage_users(monkeypatch):
    monkeypatch.setattr(auth,"session_user",lambda token:{"username":"operator","role":"Backup Operator"})
    with TestClient(module.app) as client:
        assert client.get("/api/auth/me").json()["role"]=="Backup Operator"
        assert client.get("/api/users").status_code==403


class Cursor:
    def __init__(self,rows):self.rows=iter(rows);self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,sql,args=None):self.sql.append(sql)
    def fetchone(self):return next(self.rows)


class Conn:
    def __init__(self,rows):self.cur=Cursor(rows)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def cursor(self,**kwargs):return self.cur
    def close(self):pass


def test_last_admin_and_self_access_changes_are_rejected(monkeypatch):
    import pytest
    for rows,target in [([("Admin",True),("Admin",True),(1,)],"otheradmin"),([("Admin",True),("Admin",True),(2,)],"admin")]:
        conn=Conn(rows)
        monkeypatch.setattr(auth.Store,"connect",lambda self:conn)
        with pytest.raises(ValueError):auth.change_user(target,"Viewer",False,"admin")
        assert not any(sql.startswith("UPDATE app_users") for sql in conn.cur.sql)


def test_disabled_account_revokes_sessions_and_is_audited(monkeypatch):
    conn=Conn([("Admin",True),("Viewer",True)])
    monkeypatch.setattr(auth.Store,"connect",lambda self:conn)
    auth.change_user("viewer","Viewer",False,"admin")
    assert any("UPDATE app_sessions SET revoked=true" in sql for sql in conn.cur.sql)
    assert any("identity.changed" in sql for sql in conn.cur.sql)


def test_shared_monitoring_cache_does_not_share_action_permissions(monkeypatch):
    import copy
    payload={'capabilities':{'controls':True},'sourceErrors':{},'connection':'connected'}
    async def snapshot(refresh=False):return payload
    g=FakeGateway();g.snapshot=snapshot
    monkeypatch.setattr(module,'gateway',lambda:g)
    role={'value':'Viewer'}
    monkeypatch.setattr(auth,'session_user',lambda token:{'username':'test','role':role['value']})
    with TestClient(module.app) as client:
        assert client.get('/api/snapshot').json()['capabilities']['controls'] is False
        role['value']='Admin'
        assert client.get('/api/snapshot').json()['capabilities']['controls'] is True
    assert payload['capabilities']['controls'] is True


def test_other_actor_cannot_replay_an_operations_key(monkeypatch):
    holder={}
    def gateway():
        if 'g' not in holder:holder['g']=FakeGateway()
        return holder['g']
    monkeypatch.setattr(module,'gateway',gateway)
    name={'value':'alice'}
    monkeypatch.setattr(auth,'session_user',lambda token:{'username':name['value'],'role':'Admin'})
    body={'kind':'run','target':'VMware-safe','idempotency_key':str(uuid4()),'confirmed':True}
    with TestClient(module.app) as client:
        assert client.post('/api/operations',headers=HEADERS,json=body).status_code==202
        name['value']='bob'
        assert client.post('/api/operations',headers=HEADERS,json=body).status_code==409
        assert len(holder['g'].store.rows)==1



def test_operator_cannot_prepare_isolated_restore(monkeypatch):
    monkeypatch.setattr(auth,'session_user',lambda token:{'username':'operator','role':'Backup Operator'})
    with TestClient(module.app) as client:
        assert client.post('/api/operations',headers=HEADERS,json={'kind':'restore','target':'1','idempotency_key':str(uuid4()),'confirmed':True}).status_code==403
