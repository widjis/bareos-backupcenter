"""Verify lifecycle SQL against PostgreSQL in a newly owned disposable schema.

No Bareos operation is dispatched. The isolated schema is removed after verification.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg2
from dotenv import dotenv_values

from backend.persistence import Store
from backend.lifecycle_store import LifecycleStore, AlreadyClaimed
from scripts.apply_lifecycle_migrations import PinnedPostgresAdmin, ROOT


def run_probe():
    base = Store()
    admin = PinnedPostgresAdmin(dotenv_values(ROOT / ".env"))
    schema = "lifecycle_accept_b6_" + uuid4().hex[:12]
    marker = "owned lifecycle adapter probe " + uuid4().hex
    assert re.fullmatch(r"lifecycle_accept_b6_[0-9a-f]{12}", schema)
    ddl = (ROOT / "backend/migrations/011_lifecycle_journal.sql").read_text().replace("backupcenter.", schema + ".")
    checks = []
    try:
        admin.sql("BEGIN; CREATE SCHEMA " + schema + "; COMMENT ON SCHEMA " + schema + " IS '" + marker + "'; CREATE TABLE " + schema + ".connections (id uuid PRIMARY KEY,name text,provider text); CREATE TABLE " + schema + ".audit_events(connection_id uuid,actor text,event_type text,details jsonb); GRANT USAGE ON SCHEMA " + schema + " TO backupcenter_runtime; GRANT SELECT,INSERT,UPDATE ON " + schema + ".connections TO backupcenter_runtime; GRANT SELECT,INSERT ON " + schema + ".audit_events TO backupcenter_runtime; " + ddl + " COMMIT;")
        kwargs = dict(base.kwargs, options="-c statement_timeout=10000 -c search_path=" + schema + ",pg_catalog")
        factory = lambda: psycopg2.connect(**kwargs)
        cid, other_cid = str(uuid4()), str(uuid4())
        store = LifecycleStore(connection_factory=factory, connection_id=cid)
        other = LifecycleStore(connection_factory=factory, connection_id=other_cid)
        key = str(uuid4())
        record = {"intentId":key,"actor":"lifecycle-adapter-probe","action":"clone_job","sourceJobName":"VMware-PROBE-SOURCE","newJobName":"VMware-PROBE-TARGET","newVmUuid":str(uuid4()),"selectedRepositoryId":"repo-PROBE","reviewDigest":"a"*64,"intentBinding":"b"*64,"state":"Dispatching","response":{"readiness":"dispatching","proofRevision":1,"summary":"Isolated PostgreSQL adapter probe"}}
        barrier = Barrier(2)
        def claim():
            tx=store.begin()
            barrier.wait(timeout=15)
            try:
                tx.insert_intent(key, record)
                tx.commit()
                return "claimed"
            except AlreadyClaimed:
                tx.rollback()
                return "replayed"
            except Exception:
                tx.rollback()
                raise
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: claim(), range(2)))
        assert sorted(results)==["claimed","replayed"], results
        checks.append("same-key concurrent claim dispatches once")
        assert store.get_intent(key)["state"]=="Dispatching"
        assert other.get_intent(key) is None
        tx=other.begin();tx.insert_intent(key, record);tx.commit()
        assert other.get_intent(key)["intentId"]==key
        checks.append("same external key is isolated across connections")
        tx=store.begin()
        tx.update_intent(key, {**record,"state":"Unknown","response":{"summary":"Unknown probe","readiness":"unknown"}})
        tx.commit()
        assert store.get_intent(key)["state"]=="Unknown"
        tx=store.begin()
        try:
            tx.insert_intent(str(uuid4()), record)
            raise AssertionError("Unresolved target was claimed twice")
        except AlreadyClaimed:
            tx.rollback()
        checks.append("unknown receipt retains target claims")
        retire_key=str(uuid4())
        intent={"id":str(uuid4()),"actor":"lifecycle-adapter-probe","idempotencyKey":retire_key,"jobName":"VMware-PROBE-RETIRE","reviewDigest":"c"*64,"proofRevision":1}
        operation=store.create_retirement_operation(intent)
        try:
            store.create_retirement_operation(intent)
            raise AssertionError("Retirement same-key claim repeated")
        except AlreadyClaimed:
            pass
        checks.append("retirement repeated claim is rejected")
        before={"path":"/probe-only/job.conf","digest":"d"*64,"exists":True,"captureId":"probe-only-opaque-handle"}
        retirement={"state":"Prepared","operationId":operation["id"],"jobName":intent["jobName"],"stableId":str(uuid4()),"vmInstanceUuid":str(uuid4()),"repositoryId":"repo-PROBE","configurationRevisionId":str(uuid4()),"proofRevision":1,"jobRevision":1,"stableVmRevision":1,"repositoryRevision":1,"beforeImage":before,"retainedRecovery":{"recoveryPointCount":0,"latestJobIds":[],"catalogReferenceIds":[],"mediaReadableVerified":False},"retainedObligations":["Probe only; no media ownership"]}
        store.save_retirement_record(operation["id"],retirement)
        result={"jobName":intent["jobName"],"summary":"Unknown isolated probe","readiness":"unknown","retirementRecord":{"retiredAt":None}}
        store.finalize_retirement_operation(operation["id"],"Unknown",result)
        store.finalize_retirement_operation(operation["id"],"Applied",result)
        assert store.load_retirement_operation(retire_key)["state"]=="Unknown"
        assert other.load_retirement_record(intent["jobName"]) is None
        assert "content" not in json.dumps(store.load_retirement_record(intent["jobName"]), default=str)
        checks.append("retirement unknown CAS and cross-connection isolation")
        with factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT has_table_privilege(current_user,%s,'DELETE'),has_table_privilege(current_user,%s,'DELETE')", (schema+'.lifecycle_operations',schema+'.lifecycle_operation_claims'))
                assert cursor.fetchone()==(False,True)
        checks.append("runtime cannot delete operation receipts")
        return checks
    finally:
        # Resolve ownership from the database, not a guessed path or broad prefix.
        owned=admin.sql("SELECT count(*) FROM pg_namespace WHERE nspname='"+schema+"' AND obj_description(oid,'pg_namespace')='"+marker+"';")
        if owned=="1":
            admin.sql("DROP SCHEMA " + schema + " CASCADE;")
        elif owned!="0":
            raise RuntimeError("Disposable probe ownership could not be reconciled; no cleanup issued.")


if __name__ == "__main__":
    try:
        checks=run_probe()
        print(json.dumps({"status":"passed","checks":checks,"schema_cleanup":"verified-owned probe removed","bareos_dispatch":False}))
    except Exception as exc:
        print(json.dumps({"status":"failed","errorType":type(exc).__name__,"message":"PostgreSQL adapter acceptance failed; no Bareos operation was dispatched. Review the local probe before enabling lifecycle writes."}))
        raise SystemExit(1)
