"""Local application identities; no password or raw session token is persisted."""
import hashlib
import hmac
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from psycopg2.extras import RealDictCursor
from backend.persistence import Store

COOKIE = "backupcenter_session"


def password_hash(password):
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,600000,dklen=32)
    return "pbkdf2_sha256$600000$"+salt.hex()+"$"+digest.hex()


def verify_password(password, encoded):
    try:
        method,rounds,salt,digest=encoded.split("$")
        if method!="pbkdf2_sha256" or int(rounds)!=600000: return False
        expected=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(rounds),dklen=32)
        return hmac.compare_digest(expected.hex(),digest)
    except (ValueError,TypeError):return False


@lru_cache(maxsize=1)
def dummy_hash(): return password_hash(secrets.token_urlsafe(32))


def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()


def session_user(token):
    if not token or len(token)>128:return None
    with closing(Store().connect()) as conn:
        with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT u.username,u.role FROM app_sessions s JOIN app_users u USING(username) WHERE s.token_hash=%s AND NOT s.revoked AND s.expires_at>now() AND u.enabled", (token_hash(token),))
            row=cur.fetchone()
            return dict(row) if row else None


def login(username,password):
    store=Store()
    with closing(store.connect()) as conn:
        with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users WHERE username=%s FOR UPDATE",(username,))
            row=cur.fetchone()
            valid=verify_password(password,row["password_hash"] if row else dummy_hash())
            now=datetime.now(timezone.utc)
            blocked=row and row["locked_until"] and row["locked_until"]>now
            if not row or not valid or not row["enabled"] or blocked:
                if row and not blocked:
                    failures=row["failures"]+1
                    cur.execute("UPDATE app_users SET failures=%s,locked_until=%s WHERE username=%s",(failures,now+timedelta(minutes=15) if failures>=5 else None,username))
                return None
            cur.execute("UPDATE app_users SET failures=0,locked_until=NULL WHERE username=%s",(username,))
            token=secrets.token_urlsafe(32)
            cur.execute("INSERT INTO app_sessions(token_hash,username,expires_at) VALUES(%s,%s,%s)",(token_hash(token),username,now+timedelta(hours=8)))
            cur.execute("INSERT INTO audit_events(actor,event_type,details) VALUES(%s,'auth.login','{}')",(username,))
            return {"username":username,"role":row["role"],"token":token}


def logout(token):
    with closing(Store().connect()) as conn:
        with conn,conn.cursor() as cur:
            cur.execute("UPDATE app_sessions SET revoked=true WHERE token_hash=%s",(token_hash(token or ""),))


def users():
    with closing(Store().connect()) as conn:
        with conn,conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT username,role,enabled,created_at FROM app_users ORDER BY username LIMIT 200")
            return [dict(row) for row in cur.fetchall()]


def create_user(username,password,role,actor):
    from psycopg2.extras import Json
    with closing(Store().connect()) as conn:
        with conn,conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(73124412)")
            cur.execute("SELECT role,enabled FROM app_users WHERE username=%s FOR UPDATE",(actor,))
            if cur.fetchone()!=("Admin",True):raise PermissionError("Administrator permission was revoked.")
            cur.execute("INSERT INTO app_users(username,password_hash,role) VALUES(%s,%s,%s) ON CONFLICT(username) DO NOTHING RETURNING username",(username,password_hash(password),role))
            if not cur.fetchone():raise ValueError("This username already exists.")
            cur.execute("INSERT INTO audit_events(actor,event_type,details) VALUES(%s,'identity.created',%s)",(actor,Json({"username":username,"role":role})))


def change_password(username,current,password):
    with closing(Store().connect()) as conn:
        with conn,conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM app_users WHERE username=%s FOR UPDATE",(username,))
            row=cur.fetchone()
            if not row or not verify_password(current,row[0]):raise ValueError("Current password is incorrect.")
            cur.execute("UPDATE app_users SET password_hash=%s WHERE username=%s",(password_hash(password),username))
            cur.execute("UPDATE app_sessions SET revoked=true WHERE username=%s",(username,))
            cur.execute("INSERT INTO audit_events(actor,event_type,details) VALUES(%s,'auth.password_changed','{}')",(username,))



def change_user(username,role,enabled,actor):
    from psycopg2.extras import Json
    with closing(Store().connect()) as conn:
        with conn,conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(73124412)")
            cur.execute("SELECT role,enabled FROM app_users WHERE username=%s FOR UPDATE",(actor,))
            admin=cur.fetchone()
            if not admin or admin!=("Admin",True):raise PermissionError("Administrator permission was revoked.")
            cur.execute("SELECT role,enabled FROM app_users WHERE username=%s FOR UPDATE",(username,))
            user=cur.fetchone()
            if not user:raise ValueError("Account does not exist.")
            if user==("Admin",True) and (role!="Admin" or not enabled):
                cur.execute("SELECT count(*) FROM app_users WHERE enabled AND role='Admin'")
                if cur.fetchone()[0]<=1:raise ValueError("Keep at least one enabled Admin account.")
            if username==actor and (role!="Admin" or not enabled):raise ValueError("Use another Admin to change your own access.")
            cur.execute("UPDATE app_users SET role=%s,enabled=%s WHERE username=%s",(role,enabled,username))
            if not enabled:cur.execute("UPDATE app_sessions SET revoked=true WHERE username=%s",(username,))
            cur.execute("INSERT INTO audit_events(actor,event_type,details) VALUES(%s,'identity.changed',%s)",(actor,Json({"username":username,"role":role,"enabled":enabled})))
