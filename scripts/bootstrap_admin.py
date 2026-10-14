"""Create the initial local Admin once; credentials stay in ignored local settings."""
import json
import secrets
from contextlib import closing
from dotenv import dotenv_values
from backend.auth import password_hash
from backend.persistence import Store, ROOT

path=ROOT/".env"
values=dotenv_values(path)
password=values.get("BACKUPCENTER_ADMIN_PASSWORD") or secrets.token_urlsafe(32)
if not values.get("BACKUPCENTER_ADMIN_PASSWORD"):
    with path.open("a") as f:f.write("\n# Initial application Admin login; backend/test bootstrap only.\nBACKUPCENTER_ADMIN_USERNAME=admin\nBACKUPCENTER_ADMIN_PASSWORD="+json.dumps(password)+"\n")
    path.chmod(0o600)
with closing(Store().connect()) as conn:
    with conn,conn.cursor() as cur:
        cur.execute("INSERT INTO app_users(username,password_hash,role) VALUES('admin',%s,'Admin') ON CONFLICT(username) DO NOTHING",(password_hash(password),))
print("Initial Admin exists. Login settings are in local .env; no credential printed.")
