"""Compose production lifecycle persistence without changing the operational journal."""
from contextlib import closing

from backend.lifecycle_store import LifecycleStore
from backend.managed_registry import ManagedRegistryRepository


class RegistryBackedStore:
    """Keep released onboarding staging separate from authoritative live identity."""
    def __init__(self, base_store):
        self.base_store = base_store
        self.registry = ManagedRegistryRepository(base_store)

    def __getattr__(self, name):
        return getattr(self.base_store, name)

    def assignment_detail(self, job_name):
        return self.registry.assignment_detail(job_name)


def compose_lifecycle_store(base_store):
    managed = RegistryBackedStore(base_store)
    return LifecycleStore(managed), managed.registry


def database_foundation_status(store):
    required = {
        "managed_registry_entries": ("SELECT", "INSERT", "UPDATE"),
        "managed_registry_receipts": ("SELECT", "INSERT", "UPDATE"),
        "lifecycle_operations": ("SELECT", "INSERT", "UPDATE"),
        "lifecycle_operation_claims": ("SELECT", "INSERT", "DELETE"),
        "lifecycle_retirement_records": ("SELECT", "INSERT", "UPDATE"),
    }
    try:
        with closing(store.connect()) as connection:
            with connection.cursor() as cursor:
                missing = []
                for name, permissions in required.items():
                    qualified = "backupcenter." + name
                    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (qualified,))
                    if not cursor.fetchone()[0]:
                        missing.append(name)
                        continue
                    for permission in permissions:
                        cursor.execute("SELECT has_table_privilege(current_user,%s,%s)", (qualified, permission))
                        if not cursor.fetchone()[0]:
                            missing.append(name + ":" + permission)
                count = 0
                if not any(item.startswith("managed_registry_entries") for item in missing):
                    cursor.execute("SELECT count(*) FROM backupcenter.managed_registry_entries WHERE connection_id=%s", (store.connection_id,))
                    count = cursor.fetchone()[0]
        return {"registryStoreReady": not any(item.startswith("managed_registry") for item in missing), "durableStoreReady": not any(item.startswith("lifecycle_") for item in missing), "managedJobs": count, "missingPrerequisites": missing}
    except Exception:
        return {"registryStoreReady": False, "durableStoreReady": False, "managedJobs": 0, "missingPrerequisites": ["Database lifecycle foundations are unavailable."]}


def configure_lifecycle_components(gateway):
    """Attach actual adapters; readiness remains a fresh independent check."""
    from backend.lifecycle_collectors import ProductionLifecycleCollectors
    from backend.lifecycle_executors import RemoteCloneExecutor, RemoteRetirementConfigExecutor
    collectors = ProductionLifecycleCollectors(gateway.store, gateway.lifecycle_registry)
    gateway.lifecycle_clone_collector = collectors
    gateway.lifecycle_retirement_collector = collectors
    gateway.lifecycle_clone_executor = RemoteCloneExecutor()
    gateway.lifecycle_retirement_executor = RemoteRetirementConfigExecutor()


def production_extra_readiness(gateway):
    """A method-shaped adapter or installed helper alone never enables Apply."""
    database = database_foundation_status(gateway.store)
    enabled = gateway.values.get("BACKUPCENTER_LIFECYCLE_APPLY_ENABLED") == "1"
    caps = {}
    if enabled:
        from backend.lifecycle_target import candidate_capabilities
        caps = candidate_capabilities(gateway.values)
    accepted = enabled and caps.get("applyEnabled") is True
    return {
        "installedReady": caps.get("installedReady") is True,
        "transportReady": caps.get("transportReady") is True,
        "collectorReady": all(callable(getattr(getattr(gateway, attr, None), method, None)) for attr, method in (("lifecycle_clone_collector", "collect_clone_review"), ("lifecycle_retirement_collector", "collect_retirement_proof"))),
        "durableStoreReady": database["registryStoreReady"] and database["durableStoreReady"],
        "executorReady": bool(accepted),
        "applyEnabled": bool(accepted),
    }
