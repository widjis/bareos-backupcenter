"""Backend adapters for native lifecycle clone and retirement executors."""
from __future__ import annotations

from typing import Any

from backend import lifecycle_target


def _has_methods(value: Any, names: tuple[str, ...]) -> bool:
    return bool(value) and all(callable(getattr(value, name, None)) for name in names)


def extra_readiness(values: dict[str, Any], *, clone_collector: Any = None, retirement_collector: Any = None, store: Any = None) -> dict[str, bool]:
    caps = lifecycle_target.candidate_capabilities(values)
    return {
        "installedReady": bool(caps.get("installedReady")),
        "transportReady": bool(caps.get("transportReady")),
        "collectorReady": _has_methods(clone_collector, ("collect_clone_review",)) and _has_methods(retirement_collector, ("collect_retirement_proof",)),
        "durableStoreReady": _has_methods(store, ("get_intent", "begin", "load_retirement_operation", "create_retirement_operation", "save_retirement_record", "finalize_retirement_operation", "load_retirement_record")),
        "executorReady": bool(caps.get("reviewedReady")),
    }


class RemoteCloneExecutor:
    def apply_clone(self, native_candidate: dict[str, Any], *, actor: str, intent_id: str) -> dict[str, Any]:
        return lifecycle_target.invoke(
            {
                "action": "clone_apply",
                "native_candidate": native_candidate,
                "actor": actor,
                "intent_id": intent_id,
            }
        )


class RemoteRetirementConfigExecutor:
    def capture_job_config(self, job_name: str, *, actor: str | None = None, intent_id: str | None = None, review_digest: str | None = None) -> dict[str, Any]:
        return lifecycle_target.invoke(
            {
                "action": "retirement_capture",
                "job_name": job_name,
                "actor": actor,
                "intent_id": intent_id,
                "review_digest": review_digest,
            }
        )

    def delete_job_config(
        self,
        job_name: str,
        *,
        expected_path: str,
        expected_digest: str,
        actor: str | None = None,
        intent_id: str | None = None,
        review_digest: str | None = None,
    ) -> dict[str, Any]:
        return lifecycle_target.invoke(
            {
                "action": "retirement_delete",
                "job_name": job_name,
                "expected_path": expected_path,
                "expected_digest": expected_digest,
                "actor": actor,
                "intent_id": intent_id,
                "review_digest": review_digest,
            }
        )

    def read_job_config(self, job_name: str) -> dict[str, Any]:
        return lifecycle_target.invoke({"action": "retirement_read", "job_name": job_name})

    def restore_job_config(
        self,
        beforeimage: dict[str, Any],
        *,
        actor: str | None = None,
        intent_id: str | None = None,
        review_digest: str | None = None,
        expected_destination_digest: str | None = None,
    ) -> dict[str, Any]:
        return lifecycle_target.invoke(
            {
                "action": "retirement_restore",
                "beforeimage": beforeimage,
                "actor": actor,
                "intent_id": intent_id,
                "review_digest": review_digest,
                "expected_destination_digest": expected_destination_digest,
            }
        )
