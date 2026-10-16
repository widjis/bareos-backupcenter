"""PostgreSQL-backed durable lifecycle receipts for clone and retirement flows."""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg2.extras import Json, RealDictCursor


_CLONE_TERMINAL = {"Applied", "Failed"}
_RETIREMENT_TERMINAL = {"Applied", "Failed", "Unknown"}
_UNRESOLVED = {"Prepared", "Dispatching", "Unknown"}
_OPAQUE_BEFOREIMAGE_KEYS = ("receiptId", "receipt", "reference", "referenceId", "helperReceipt", "captureId", "handle", "opaqueRef")


class AlreadyClaimed(ValueError):
    """Raised when a lifecycle idempotency key or target claim is already durable."""


def _unwrap(value: Any) -> Any:
    return getattr(value, "adapted", value)


def _exec(cur: Any, tag: str, sql: str, params: tuple[Any, ...] = ()) -> None:
    if hasattr(cur, "execute_tag"):
        cur.execute_tag(tag, tuple(_unwrap(item) for item in params))
        return
    cur.execute(f"/* {tag} */ {sql}", params)


def _clone_claims(record: dict[str, Any]) -> list[str]:
    return [
        f"job:{record['sourceJobName']}",
        f"job:{record['newJobName']}",
        f"vm:{record['newVmUuid']}",
    ]


def _retirement_claims(job_name: str) -> list[str]:
    return [f"job:{job_name}"]


def _sanitize_beforeimage(beforeimage: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    has_content = "content" in beforeimage and beforeimage.get("content") is not None
    if has_content and not any(beforeimage.get(key) for key in _OPAQUE_BEFOREIMAGE_KEYS):
        raise ValueError("Durable before-image capture requires an opaque helper receipt or handle when raw content is present.")
    private = {
        "path": beforeimage.get("path"),
        "digest": beforeimage.get("digest"),
        "exists": bool(beforeimage.get("exists")),
        "redacted": has_content,
    }
    if has_content:
        private["redactedBytes"] = len(str(beforeimage["content"]))
    reference = {
        key: beforeimage[key]
        for key in (
            "path",
            "digest",
            "exists",
            "receiptId",
            "receipt",
            "reference",
            "referenceId",
            "helperReceipt",
            "captureId",
            "handle",
            "opaqueRef",
        )
        if key in beforeimage and key != "content"
    }
    if not reference:
        reference = {
            "path": beforeimage.get("path"),
            "digest": beforeimage.get("digest"),
            "exists": bool(beforeimage.get("exists")),
            "redacted": True,
        }
    return private, reference


def _clone_record(row: dict[str, Any]) -> dict[str, Any]:
    intent = deepcopy(row.get("intent") or {})
    return {
        "intentId": str(row.get("idempotency_key") or row["id"]),
        "actor": row["actor"],
        "action": row["action"],
        "sourceJobName": row.get("source_job_name") or intent.get("sourceJobName"),
        "newJobName": row.get("new_job_name") or intent.get("newJobName"),
        "newVmUuid": row.get("new_vm_uuid") or intent.get("newVmUuid"),
        "selectedRepositoryId": row.get("repository_id") or intent.get("selectedRepositoryId"),
        "reviewDigest": row["review_digest"],
        "intentBinding": row["intent_binding"],
        "state": row["state"],
        "response": deepcopy(row.get("result") or {}),
    }


def _retirement_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "state": row["state"],
        "intent": deepcopy(row.get("intent") or {}),
        "result": deepcopy(row.get("result") or {}),
    }


class LifecycleStoreTransaction:
    def __init__(self, connection_factory: Any, connection_id: str):
        self._connection = connection_factory()
        self._connection_id = connection_id
        self._closed = False

    def _cursor(self) -> Any:
        return self._connection.cursor(cursor_factory=RealDictCursor)

    def _operation_id(self, intent_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"lifecycle-clone:{self._connection_id}:{intent_id}"))

    def _lock_keys(self, cur: Any, *keys: str) -> None:
        for key in sorted(set(keys)):
            _exec(
                cur,
                "lifecycle.lock",
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"{self._connection_id}:{key}",),
            )

    def insert_intent(self, intent_id: str, record: dict[str, Any]) -> None:
        claims = _clone_claims(record)
        with closing(self._cursor()) as cur:
            _exec(
                cur,
                "lifecycle.ensure_connection",
                "INSERT INTO connections(id, name, provider) VALUES(%s, 'Bareos Director', 'bareos') ON CONFLICT(id) DO NOTHING",
                (self._connection_id,),
            )
            self._lock_keys(cur, f"key:{intent_id}", *[f"claim:{claim}" for claim in claims])
            _exec(
                cur,
                "lifecycle.select_operation_by_key",
                "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND idempotency_key=%s",
                (self._connection_id, intent_id),
            )
            existing = cur.fetchone()
            if existing:
                if existing["intent_binding"] != record["intentBinding"]:
                    raise ValueError("Idempotency key belongs to another lifecycle intent.")
                raise AlreadyClaimed("Idempotency key is already durably claimed for this lifecycle intent.")
            for claim in claims:
                _exec(
                    cur,
                    "lifecycle.select_claim",
                    "SELECT c.claim_key, o.idempotency_key FROM lifecycle_operation_claims c JOIN lifecycle_operations o ON o.connection_id=c.connection_id AND o.id=c.operation_id WHERE c.connection_id=%s AND c.claim_key=%s",
                    (self._connection_id, claim),
                )
                if cur.fetchone():
                    raise AlreadyClaimed("A lifecycle operation already holds this target claim.")
            result = deepcopy(record["response"])
            intent = {
                "intentId": intent_id,
                "action": record["action"],
                "sourceJobName": record["sourceJobName"],
                "newJobName": record["newJobName"],
                "newVmUuid": record["newVmUuid"],
                "selectedRepositoryId": record["selectedRepositoryId"],
                "reviewDigest": record["reviewDigest"],
                "actor": record["actor"],
            }
            _exec(
                cur,
                "lifecycle.insert_operation",
                """
                INSERT INTO lifecycle_operations(
                    id, connection_id, idempotency_key, kind, action, actor, state,
                    review_digest, proof_revision, intent_binding, job_name,
                    source_job_name, new_job_name, new_vm_uuid, repository_id, intent, result
                ) VALUES(%s,%s,%s,'clone',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    self._operation_id(intent_id),
                    self._connection_id,
                    intent_id,
                    record["action"],
                    record["actor"],
                    record["state"],
                    record["reviewDigest"],
                    int(result.get("proofRevision") or 0),
                    record["intentBinding"],
                    record["newJobName"],
                    record["sourceJobName"],
                    record["newJobName"],
                    record["newVmUuid"],
                    record["selectedRepositoryId"],
                    Json(intent),
                    Json(result),
                ),
            )
            for claim in claims:
                _exec(
                    cur,
                    "lifecycle.insert_claim",
                    "INSERT INTO lifecycle_operation_claims(connection_id, claim_key, operation_id) VALUES(%s, %s, %s)",
                    (self._connection_id, claim, self._operation_id(intent_id)),
                )
            _exec(
                cur,
                "lifecycle.insert_audit",
                "INSERT INTO audit_events(connection_id, actor, event_type, details) VALUES(%s, %s, %s, %s)",
                (
                    self._connection_id,
                    record["actor"],
                    "lifecycle.clone.dispatching",
                    Json(
                        {
                            "jobName": record["newJobName"],
                            "sourceJobName": record["sourceJobName"],
                            "idempotencyKey": intent_id,
                            "state": record["state"],
                            "action": record["action"],
                        }
                    ),
                ),
            )

    def update_intent(self, intent_id: str, record: dict[str, Any]) -> None:
        with closing(self._cursor()) as cur:
            _exec(
                cur,
                "lifecycle.select_operation_by_id",
                "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND id=%s",
                (self._connection_id, self._operation_id(intent_id)),
            )
            existing = cur.fetchone()
            if not existing:
                raise KeyError(intent_id)
            if existing["intent_binding"] != record["intentBinding"]:
                raise ValueError("Lifecycle intent binding mismatch.")
            current_state = existing["state"]
            next_state = record["state"]
            if current_state in _RETIREMENT_TERMINAL | _CLONE_TERMINAL and current_state != next_state:
                return
            _exec(
                cur,
                "lifecycle.update_operation",
                "UPDATE lifecycle_operations SET state=%s, result=%s, updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",
                (next_state, Json(deepcopy(record["response"])), self._connection_id, self._operation_id(intent_id)),
            )
            if next_state in _CLONE_TERMINAL:
                _exec(
                    cur,
                    "lifecycle.delete_claims",
                    "DELETE FROM lifecycle_operation_claims WHERE connection_id=%s AND operation_id=%s",
                    (self._connection_id, self._operation_id(intent_id)),
                )
            _exec(
                cur,
                "lifecycle.insert_audit",
                "INSERT INTO audit_events(connection_id, actor, event_type, details) VALUES(%s, %s, %s, %s)",
                (
                    self._connection_id,
                    record["actor"],
                    f"lifecycle.clone.{next_state.lower()}",
                    Json(
                        {
                            "jobName": record["newJobName"],
                            "sourceJobName": record["sourceJobName"],
                            "idempotencyKey": intent_id,
                            "state": next_state,
                            "action": record["action"],
                        }
                    ),
                ),
            )

    def read_intent(self, intent_id: str) -> dict[str, Any]:
        with closing(self._cursor()) as cur:
            _exec(
                cur,
                "lifecycle.select_operation_by_id",
                "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND id=%s",
                (self._connection_id, self._operation_id(intent_id)),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError(intent_id)
            return _clone_record(row)

    def commit(self) -> None:
        self._connection.commit()
        self._closed = True
        self._connection.close()

    def rollback(self) -> None:
        if not self._closed:
            try:
                self._connection.rollback()
            finally:
                self._connection.close()
                self._closed = True


class LifecycleStore:
    """Concrete PostgreSQL adapter for clone and retirement durability."""

    def __init__(self, store: Any | None = None, *, connection_factory: Any | None = None, connection_id: str | None = None):
        self._delegate = store
        self._connection_factory = connection_factory or getattr(store, "connect", None)
        self.connection_id = connection_id or getattr(store, "connection_id", None)
        if not self._connection_factory or not self.connection_id:
            raise ValueError("LifecycleStore requires connection_factory and connection_id.")

    def __getattr__(self, name: str) -> Any:
        if self._delegate is None:
            raise AttributeError(name)
        return getattr(self._delegate, name)

    def actor_allowed(self, username: str, kind: str = "run") -> bool:
        if not self._delegate or not hasattr(self._delegate, "actor_allowed"):
            raise AttributeError("Delegated Store.actor_allowed is unavailable.")
        return bool(self._delegate.actor_allowed(username, kind))

    def begin(self) -> LifecycleStoreTransaction:
        return LifecycleStoreTransaction(self._connection_factory, self.connection_id)

    def _connect(self) -> Any:
        return self._connection_factory()

    def get_intent(self, intent_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            _exec(
                cur,
                "lifecycle.select_operation_by_id_or_key",
                "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND (id=%s OR idempotency_key=%s) ORDER BY created_at DESC LIMIT 1",
                (self.connection_id, intent_id, intent_id),
            )
            row = cur.fetchone()
            return _clone_record(row) if row else None

    def load_retirement_operation(self, idempotency_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            _exec(
                cur,
                "lifecycle.select_operation_by_key",
                "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND idempotency_key=%s ORDER BY created_at DESC LIMIT 1",
                (self.connection_id, idempotency_key),
            )
            row = cur.fetchone()
            return _retirement_record(row) if row else None

    def create_retirement_operation(self, intent: dict[str, Any]) -> dict[str, Any]:
        claims = _retirement_claims(intent["jobName"])
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            try:
                _exec(
                    cur,
                    "lifecycle.ensure_connection",
                    "INSERT INTO connections(id, name, provider) VALUES(%s, 'Bareos Director', 'bareos') ON CONFLICT(id) DO NOTHING",
                    (self.connection_id,),
                )
                for key in sorted(set([f"key:{intent['idempotencyKey']}"] + [f"claim:{claim}" for claim in claims])):
                    _exec(
                        cur,
                        "lifecycle.lock",
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"{self.connection_id}:{key}",),
                    )
                _exec(
                    cur,
                    "lifecycle.select_operation_by_key",
                    "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND idempotency_key=%s",
                    (self.connection_id, intent["idempotencyKey"]),
                )
                existing = cur.fetchone()
                if existing:
                    if (existing.get("intent") or {}).get("actor") != intent["actor"] or existing["review_digest"] != intent["reviewDigest"] or (existing.get("intent") or {}).get("jobName") != intent["jobName"]:
                        raise ValueError("Request key belongs to another retirement intent.")
                    raise AlreadyClaimed("Retirement idempotency key is already durably claimed.")
                for claim in claims:
                    _exec(
                        cur,
                        "lifecycle.select_claim",
                        "SELECT c.claim_key, o.idempotency_key FROM lifecycle_operation_claims c JOIN lifecycle_operations o ON o.connection_id=c.connection_id AND o.id=c.operation_id WHERE c.connection_id=%s AND c.claim_key=%s",
                        (self.connection_id, claim),
                    )
                    if cur.fetchone():
                        raise AlreadyClaimed("An unresolved lifecycle operation already exists for this target.")
                result = {
                    "jobName": intent["jobName"],
                    "readiness": "prepared",
                    "summary": "Retirement claim is durable; persist the before-image before any delete attempt.",
                }
                _exec(
                    cur,
                    "lifecycle.insert_operation",
                    """
                    INSERT INTO lifecycle_operations(
                        id, connection_id, idempotency_key, kind, action, actor, state,
                        review_digest, proof_revision, intent_binding, job_name, source_job_name,
                        new_job_name, new_vm_uuid, repository_id, intent, result
                    ) VALUES(%s,%s,%s,'remove','remove_configuration',%s,'Prepared',%s,%s,%s,%s,NULL,NULL,NULL,NULL,%s,%s)
                    RETURNING *
                    """,
                    (
                        intent["id"],
                        self.connection_id,
                        intent["idempotencyKey"],
                        intent["actor"],
                        intent["reviewDigest"],
                        int(intent["proofRevision"]),
                        f"remove:{intent['actor']}:{intent['jobName']}:{intent['reviewDigest']}",
                        intent["jobName"],
                        Json(deepcopy(intent)),
                        Json(result),
                    ),
                )
                row = cur.fetchone()
                for claim in claims:
                    _exec(
                        cur,
                        "lifecycle.insert_claim",
                        "INSERT INTO lifecycle_operation_claims(connection_id, claim_key, operation_id) VALUES(%s, %s, %s)",
                        (self.connection_id, claim, intent["id"]),
                    )
                _exec(
                    cur,
                    "lifecycle.insert_audit",
                    "INSERT INTO audit_events(connection_id, actor, event_type, details) VALUES(%s, %s, %s, %s)",
                    (
                        self.connection_id,
                        intent["actor"],
                        "lifecycle.remove.prepared",
                        Json(
                            {
                                "jobName": intent["jobName"],
                                "idempotencyKey": intent["idempotencyKey"],
                                "state": "Prepared",
                                "action": "remove_configuration",
                            }
                        ),
                    ),
                )
                conn.commit()
                return _retirement_record(row)
            except Exception:
                conn.rollback()
                raise

    def save_retirement_record(self, operation_id: str, record: dict[str, Any]) -> dict[str, Any]:
        private_beforeimage, beforeimage_ref = _sanitize_beforeimage(record["beforeImage"])
        result = {
            "jobName": record["jobName"],
            "readiness": "dispatching",
            "summary": "Retirement before-image receipt is durable. Do not resend while delete reconciliation is unresolved.",
        }
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            try:
                _exec(
                    cur,
                    "lifecycle.select_operation_by_id",
                    "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND id=%s",
                    (self.connection_id, operation_id),
                )
                row = cur.fetchone()
                if not row:
                    raise KeyError(operation_id)
                _exec(
                    cur,
                    "lifecycle.upsert_retirement_record",
                    """
                    INSERT INTO lifecycle_retirement_records(
                        connection_id, job_name, operation_id, state, stable_id, vm_instance_uuid,
                        repository_id, configuration_revision_id, proof_revision, job_revision,
                        stable_vm_revision, repository_revision, retained_recovery, retained_obligations,
                        beforeimage_private, beforeimage_ref, retired_at
                    ) VALUES(%s,%s,%s,'Dispatching',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)
                    ON CONFLICT(connection_id, job_name) DO UPDATE SET
                        operation_id=excluded.operation_id,
                        state=excluded.state,
                        stable_id=excluded.stable_id,
                        vm_instance_uuid=excluded.vm_instance_uuid,
                        repository_id=excluded.repository_id,
                        configuration_revision_id=excluded.configuration_revision_id,
                        proof_revision=excluded.proof_revision,
                        job_revision=excluded.job_revision,
                        stable_vm_revision=excluded.stable_vm_revision,
                        repository_revision=excluded.repository_revision,
                        retained_recovery=excluded.retained_recovery,
                        retained_obligations=excluded.retained_obligations,
                        beforeimage_private=excluded.beforeimage_private,
                        beforeimage_ref=excluded.beforeimage_ref,
                        updated_at=now()
                    RETURNING *
                    """,
                    (
                        self.connection_id,
                        record["jobName"],
                        operation_id,
                        record["stableId"],
                        record["vmInstanceUuid"],
                        record["repositoryId"],
                        record["configurationRevisionId"],
                        int(record["proofRevision"]),
                        int(record["jobRevision"]),
                        int(record["stableVmRevision"]),
                        int(record["repositoryRevision"]),
                        Json(deepcopy(record["retainedRecovery"])),
                        Json(list(record["retainedObligations"])),
                        Json(private_beforeimage),
                        Json(beforeimage_ref),
                    ),
                )
                _exec(
                    cur,
                    "lifecycle.update_operation",
                    "UPDATE lifecycle_operations SET state='Dispatching', result=%s, updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",
                    (Json(result), self.connection_id, operation_id),
                )
                _exec(
                    cur,
                    "lifecycle.insert_audit",
                    "INSERT INTO audit_events(connection_id, actor, event_type, details) VALUES(%s, %s, %s, %s)",
                    (
                        self.connection_id,
                        row["actor"],
                        "lifecycle.remove.dispatching",
                        Json(
                            {
                                "jobName": record["jobName"],
                                "idempotencyKey": row["idempotency_key"],
                                "state": "Dispatching",
                                "action": "remove_configuration",
                            }
                        ),
                    ),
                )
                conn.commit()
                saved = deepcopy(record)
                saved["beforeImage"] = beforeimage_ref
                saved["state"] = "Dispatching"
                return saved
            except Exception:
                conn.rollback()
                raise

    def finalize_retirement_operation(self, operation_id: str, state: str, result: dict[str, Any]) -> dict[str, Any]:
        if state not in _RETIREMENT_TERMINAL:
            raise ValueError("Unsupported retirement terminal state.")
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            try:
                _exec(
                    cur,
                    "lifecycle.select_operation_by_id",
                    "SELECT * FROM lifecycle_operations WHERE connection_id=%s AND id=%s",
                    (self.connection_id, operation_id),
                )
                row = cur.fetchone()
                if not row:
                    raise KeyError(operation_id)
                if row["state"] in _RETIREMENT_TERMINAL:
                    conn.commit()
                    return _retirement_record(row)
                _exec(
                    cur,
                    "lifecycle.update_operation",
                    "UPDATE lifecycle_operations SET state=%s, result=%s, updated_at=now() WHERE connection_id=%s AND id=%s RETURNING *",
                    (state, Json(deepcopy(result)), self.connection_id, operation_id),
                )
                updated = cur.fetchone()
                _exec(
                    cur,
                    "lifecycle.update_retirement_record",
                    "UPDATE lifecycle_retirement_records SET state=%s, retired_at=%s, updated_at=now() WHERE connection_id=%s AND operation_id=%s",
                    (state, result.get("retirementRecord", {}).get("retiredAt"), self.connection_id, operation_id),
                )
                if state in {"Applied", "Failed"}:
                    _exec(
                        cur,
                        "lifecycle.delete_claims",
                        "DELETE FROM lifecycle_operation_claims WHERE connection_id=%s AND operation_id=%s",
                        (self.connection_id, operation_id),
                    )
                _exec(
                    cur,
                    "lifecycle.insert_audit",
                    "INSERT INTO audit_events(connection_id, actor, event_type, details) VALUES(%s, %s, %s, %s)",
                    (
                        self.connection_id,
                        row["actor"],
                        f"lifecycle.remove.{state.lower()}",
                        Json(
                            {
                                "jobName": (row.get("intent") or {}).get("jobName", row.get("job_name")),
                                "idempotencyKey": row["idempotency_key"],
                                "state": state,
                                "action": row["action"],
                            }
                        ),
                    ),
                )
                conn.commit()
                return _retirement_record(updated)
            except Exception:
                conn.rollback()
                raise

    def load_retirement_record(self, job_name: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn, closing(conn.cursor(cursor_factory=RealDictCursor)) as cur:
            _exec(
                cur,
                "lifecycle.select_retirement_record",
                """
                SELECT r.*, o.state AS operation_state, o.result AS operation_result
                FROM lifecycle_retirement_records r
                JOIN lifecycle_operations o ON o.connection_id=r.connection_id AND o.id=r.operation_id
                WHERE r.connection_id=%s AND r.job_name=%s
                ORDER BY r.updated_at DESC
                LIMIT 1
                """,
                (self.connection_id, job_name),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = deepcopy(row.get("operation_result") or {})
            return {
                "jobName": row["job_name"],
                "stableId": row["stable_id"],
                "vmInstanceUuid": row["vm_instance_uuid"],
                "repositoryId": row["repository_id"],
                "configurationRevisionId": row["configuration_revision_id"],
                "proofRevision": row["proof_revision"],
                "jobRevision": row["job_revision"],
                "stableVmRevision": row["stable_vm_revision"],
                "repositoryRevision": row["repository_revision"],
                "state": row["state"],
                "operationId": row["operation_id"],
                "retiredAt": row.get("retired_at"),
                "retainedRecovery": deepcopy(row["retained_recovery"]),
                "retainedObligations": list(row["retained_obligations"]),
                "beforeImageReference": deepcopy(row["beforeimage_ref"]),
                "finalResult": result,
            }
