"""Pure preview planner for managed job lifecycle actions; never executes changes."""
import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import to_jsonable_python

SAFE_JOB_NAME = r"^[A-Za-z0-9][A-Za-z0-9 ._-]{2,79}$"
SAFE_KEY = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
NONTERMINAL_OPERATION_STATES = {"active", "waiting", "prepared", "dispatching", "unknown"}
UNSUPPORTED_NOTES = (
    "Multi-VM jobs remain unsupported by this contract.",
    "Backup-data deletion is outside this preview contract.",
    "Secret copying is outside this preview contract.",
)


def _dump(value):
    return json.dumps(to_jsonable_python(value), sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


def _resource_key(resource_type, resource_name):
    return f"{resource_type}:{resource_name}".lower()


class ManagedTargetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stable_id: str = Field(pattern=SAFE_KEY)
    job_name: str = Field(pattern=SAFE_JOB_NAME)
    selection_revision: int = Field(ge=1, le=1_000_000_000)
    snapshot_revision: int = Field(ge=1, le=1_000_000_000)
    identity_revision: int = Field(ge=1, le=1_000_000_000)
    managed_vm_ids: list[UUID] = Field(min_length=1, max_length=8)
    repository_id: str = Field(pattern=SAFE_KEY)

    @model_validator(mode="after")
    def unique_vm_ids(self):
        if len(self.managed_vm_ids) != len(set(self.managed_vm_ids)):
            raise ValueError("Managed VM identities must be unique.")
        return self


class ResourceUsageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    resource_type: Literal[
        "job",
        "schedule",
        "fileset",
        "pool",
        "repository",
        "preparation_mapping",
        "retention_mapping",
        "storage_mapping",
    ]
    resource_name: str = Field(pattern=SAFE_KEY)
    ownership: Literal["exclusive", "shared", "external", "unknown"]
    usage_count: int = Field(ge=0, le=10_000)
    proof_revision: int | None = Field(default=None, ge=1, le=1_000_000_000)


class OperationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    operation_id: str = Field(pattern=SAFE_KEY)
    kind: Literal["backup", "restore", "policy_apply", "lifecycle_apply", "cleanup", "other"]
    state: Literal["active", "waiting", "prepared", "dispatching", "unknown", "completed", "failed", "canceled"]
    summary: str = Field(min_length=1, max_length=200)


class DependencyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    relation: Literal["depends_on", "required_by"]
    related_stable_id: str = Field(pattern=SAFE_KEY)
    related_job_name: str = Field(pattern=SAFE_JOB_NAME)
    proof_revision: int | None = Field(default=None, ge=1, le=1_000_000_000)


class UnresolvedIntentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["delete_backup_data", "move_repository", "rename_job", "maintenance", "resource_transfer", "clone_apply", "other"]
    summary: str = Field(min_length=1, max_length=200)
    proof_revision: int | None = Field(default=None, ge=1, le=1_000_000_000)


class VmAssignmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    vm_identity: UUID
    stable_id: str = Field(pattern=SAFE_KEY)
    job_name: str = Field(pattern=SAFE_JOB_NAME)
    state: Literal["managed", "retired", "unknown"] = "managed"


class RetainedRecoveryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recovery_point_count: int = Field(ge=0, le=1_000_000)
    latest_job_ids: list[int] = Field(default_factory=list, max_length=25)
    retained_recovery_confirmed: bool | None = None
    catalog_visibility_confirmed: bool | None = None
    retention_owner_confirmed: bool | None = None
    cleanup_owner_confirmed: bool | None = None
    retirement_record_confirmed: bool | None = None

    @field_validator("latest_job_ids")
    @classmethod
    def positive_unique_job_ids(cls, value):
        if any(job_id <= 0 for job_id in value) or len(value) != len(set(value)):
            raise ValueError("Recovery job ids must be unique positive integers.")
        return sorted(value)


class LifecycleBlocker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    summary: str = Field(min_length=1, max_length=240)
    evidence_refs: list[str] = Field(default_factory=list, max_length=4)


class LifecycleImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9_]{3,64}$")
    severity: Literal["info", "warning", "obligation"]
    summary: str = Field(min_length=1, max_length=240)
    evidence_refs: list[str] = Field(default_factory=list, max_length=4)


class ResourceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: Literal["job", "schedule", "fileset", "pool"]
    resource_name: str = Field(pattern=SAFE_KEY)


class LifecyclePreviewBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["disable_schedule", "clone_draft", "remove_configuration"]
    review_status: Literal["blocked", "ready_for_confirmation"]
    eligible_for_apply: bool
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_refs: list[str] = Field(max_length=32)
    blockers: list[LifecycleBlocker] = Field(max_length=12)
    impacts: list[LifecycleImpact] = Field(max_length=12)
    unsupported: list[str] = Field(default_factory=lambda: list(UNSUPPORTED_NOTES), max_length=8)


class DisableSchedulePreview(LifecyclePreviewBase):
    action: Literal["disable_schedule"] = "disable_schedule"
    schedule_enabled_after: Literal[False] = False


class CloneDraftPreview(LifecyclePreviewBase):
    action: Literal["clone_draft"] = "clone_draft"
    source_stable_id: str = Field(pattern=SAFE_KEY)
    new_job_name: str = Field(pattern=SAFE_JOB_NAME)
    target_vm_identity: UUID
    target_repository_id: str = Field(pattern=SAFE_KEY)
    automatic_schedule: Literal[False] = False
    history_copied: Literal[False] = False
    secrets_copied: Literal[False] = False
    draft_resources: list[ResourceDraft] = Field(max_length=4)


class RemoveConfigurationPreview(LifecyclePreviewBase):
    action: Literal["remove_configuration"] = "remove_configuration"
    preserve_backup_data: Literal[True] = True
    delete_backup_data_supported: Literal[False] = False
    retained_recovery_job_ids: list[int] = Field(max_length=25)
    retained_obligations: list[str] = Field(max_length=8)


class LifecycleContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Legacy fixture/context label, never authoritative for authorization.
    actor_role: Literal["Admin", "Backup Operator", "Viewer"]
    proof_revision: int | None = Field(default=None, ge=1)
    proof_coverage: list[Literal["operations","dependencies","intents","resources","names","assignments","target_vm","target_repository"]] = Field(default_factory=list,max_length=8)
    snapshot: ManagedTargetSnapshot
    resources: list[ResourceUsageEvidence] = Field(default_factory=list, max_length=32)
    operations: list[OperationEvidence] = Field(default_factory=list, max_length=12)
    dependencies: list[DependencyEvidence] = Field(default_factory=list, max_length=12)
    unresolved_intents: list[UnresolvedIntentEvidence] = Field(default_factory=list, max_length=12)


class DisableSchedulePreviewRequest(LifecycleContext):
    pass


class CloneDraftPreviewRequest(LifecycleContext):
    new_job_name: str = Field(pattern=SAFE_JOB_NAME)
    target_vm_identity: UUID
    target_repository_id: str = Field(pattern=SAFE_KEY)
    existing_job_names: list[str] = Field(default_factory=list, max_length=512)
    existing_assignments: list[VmAssignmentEvidence] = Field(default_factory=list, max_length=512)
    requested_secret_copy: bool = False

    @field_validator("existing_job_names")
    @classmethod
    def valid_names(cls, value):
        seen = set()
        for name in value:
            if not re.fullmatch(SAFE_JOB_NAME, name):
                raise ValueError("Existing job names must use the managed safe-name contract.")
            lowered = name.casefold()
            if lowered in seen:
                raise ValueError("Existing job names must be unique.")
            seen.add(lowered)
        return value


class RemoveConfigurationPreviewRequest(LifecycleContext):
    preserve_backup_data: bool = True
    delete_backup_data_requested: bool = False
    retained_recovery: RetainedRecoveryEvidence


def _build_evidence_refs(context, extra=None):
    extra = extra or []
    snapshot = context.snapshot
    refs = {
        "coverage:"+",".join(sorted(set(context.proof_coverage)))+":revision="+str(context.proof_revision),
        f"snapshot:{snapshot.stable_id}:selected={snapshot.selection_revision}:current={snapshot.snapshot_revision}:identity={snapshot.identity_revision}",
        f"job:{snapshot.job_name}",
        f"repository:{snapshot.repository_id}",
    }
    refs.update(f"vm:{vm_id}" for vm_id in snapshot.managed_vm_ids)
    for resource in context.resources:
        refs.add(
            f"resource:{resource.resource_type}:{resource.resource_name}:ownership={resource.ownership}:usage={resource.usage_count}:proof={resource.proof_revision or 0}"
        )
    for operation in context.operations:
        refs.add(f"operation:{operation.kind}:{operation.state}:{operation.operation_id}")
    for dependency in context.dependencies:
        refs.add(
            f"dependency:{dependency.relation}:{dependency.related_stable_id}:proof={dependency.proof_revision or 0}"
        )
    for intent in context.unresolved_intents:
        refs.add(f"intent:{intent.kind}:proof={intent.proof_revision or 0}")
    refs.update(extra)
    ordered=sorted(refs)
    return ordered if len(ordered)<=32 else ordered[:31]+["evidence-set:"+_digest(ordered)]


def _add_blocker(items, code, summary, refs):
    entry = LifecycleBlocker(code=code, summary=summary, evidence_refs=sorted(set(refs))[:4])
    if entry not in items and len(items) < 12:
        items.append(entry)


def _add_impact(items, code, severity, summary, refs):
    entry = LifecycleImpact(code=code, severity=severity, summary=summary, evidence_refs=sorted(set(refs))[:4])
    if entry not in items and len(items) < 12:
        items.append(entry)


def _common_blockers(context, blockers, trusted_role):
    snapshot = context.snapshot
    snapshot_ref = f"snapshot:{snapshot.stable_id}:selected={snapshot.selection_revision}:current={snapshot.snapshot_revision}:identity={snapshot.identity_revision}"
    if trusted_role != "Admin":
        _add_blocker(
            blockers,
            "permission_denied",
            "Only an Admin may review this lifecycle action for confirmation.",
            [snapshot_ref],
        )
    needed={"operations","dependencies","intents","resources"}
    if context.proof_revision != snapshot.snapshot_revision or not needed <= set(context.proof_coverage):
        _add_blocker(blockers,"missing_registry_proof","Complete current operation, dependency, intent and resource registry evidence is required.",[snapshot_ref])
    if snapshot.selection_revision != snapshot.snapshot_revision:
        _add_blocker(
            blockers,
            "stale_snapshot",
            "The managed target snapshot changed. Reload the latest identity and configuration evidence before review.",
            [snapshot_ref],
        )
    if len(snapshot.managed_vm_ids) != 1:
        _add_blocker(
            blockers,
            "unsupported_multi_vm",
            "This preview contract supports exactly one managed VM per job.",
            [snapshot_ref],
        )
    for operation in context.operations:
        if operation.state in NONTERMINAL_OPERATION_STATES:
            _add_blocker(
                blockers,
                "pending_operation",
                f"{operation.kind.capitalize()} operation {operation.operation_id} is {operation.state} and must settle first.",
                [f"operation:{operation.kind}:{operation.state}:{operation.operation_id}"],
            )
    for intent in context.unresolved_intents:
        _add_blocker(
            blockers,
            "unresolved_intent",
            f"Resolve the pending {intent.kind.replace('_', ' ')} intent before confirming another lifecycle change.",
            [f"intent:{intent.kind}:proof={intent.proof_revision or 0}"],
        )


def _exclusive_resource_proofs(resources, blockers):
    for resource in resources:
        ref = f"resource:{resource.resource_type}:{resource.resource_name}:ownership={resource.ownership}:usage={resource.usage_count}:proof={resource.proof_revision or 0}"
        if resource.proof_revision is None or resource.ownership == "unknown":
            _add_blocker(
                blockers,
                "missing_resource_proof",
                f"Verified ownership proof is missing for {resource.resource_type} {resource.resource_name}.",
                [ref],
            )
        elif resource.ownership != "exclusive" or resource.usage_count > 1:
            _add_blocker(
                blockers,
                "shared_resource",
                f"{resource.resource_type.capitalize()} {resource.resource_name} is not proven exclusive to this job.",
                [ref],
            )


def _dependency_blockers(context, blockers, summary):
    for dependency in context.dependencies:
        ref = f"dependency:{dependency.relation}:{dependency.related_stable_id}:proof={dependency.proof_revision or 0}"
        if dependency.proof_revision is None:
            _add_blocker(
                blockers,
                "missing_dependency_proof",
                f"Dependency proof is missing for related job {dependency.related_job_name}.",
                [ref],
            )
        _add_blocker(blockers, "dependency_blocker", summary.format(job=dependency.related_job_name), [ref])


def _preview_status(blockers):
    return "ready_for_confirmation" if not blockers else "blocked"


def _finalize_preview(model, payload):
    payload["review_digest"] = _digest(
        {
            "action": payload["action"],
            "review_status": payload["review_status"],
            "eligible_for_apply": payload["eligible_for_apply"],
            "evidence_refs": payload["evidence_refs"],
            "blockers": [item.model_dump() for item in payload["blockers"]],
            "impacts": [item.model_dump() for item in payload["impacts"]],
            "details": {k: v for k, v in payload.items() if k not in {"action", "review_status", "eligible_for_apply", "evidence_refs", "blockers", "impacts", "review_digest"}},
        }
    )
    return model(**payload)


def _clone_resource_names(new_job_name):
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", new_job_name.replace(" ", "-")).strip("-")
    base = re.sub(r"-{2,}", "-", base) or "managed-clone"
    return [
        ResourceDraft(resource_type="job", resource_name=base),
        ResourceDraft(resource_type="fileset", resource_name=f"{base}.fileset"),
        ResourceDraft(resource_type="schedule", resource_name=f"{base}.schedule"),
        ResourceDraft(resource_type="pool", resource_name=f"{base}.pool"),
    ]


def preview_disable_schedule(request, *, trusted_role=None):
    request = DisableSchedulePreviewRequest.model_validate(request)
    blockers = []
    impacts = []
    _common_blockers(request, blockers, trusted_role)
    schedule_resources = [resource for resource in request.resources if resource.resource_type == "schedule"]
    if not schedule_resources:
        _add_blocker(
            blockers,
            "missing_resource_proof",
            "Provide reviewed schedule ownership and usage evidence before disabling this job.",
            [f"job:{request.snapshot.job_name}"],
        )
    _exclusive_resource_proofs(schedule_resources, blockers)
    _dependency_blockers(
        request,
        blockers,
        "Job dependency {job} must be reviewed before disabling this schedule.",
    )
    _add_impact(
        impacts,
        "schedule_disabled",
        "warning",
        "The managed job would remain present but its automatic schedule would be disabled.",
        [f"job:{request.snapshot.job_name}"],
    )
    _add_impact(
        impacts,
        "backups_preserved",
        "info",
        "Disabling the schedule does not remove backup data, recovery history or retained media.",
        [f"job:{request.snapshot.job_name}"],
    )
    _add_impact(
        impacts,
        "active_sessions_unchanged",
        "obligation",
        "Existing active or waiting sessions require their own reviewed stop/cancel decision.",
        [f"job:{request.snapshot.job_name}"],
    )
    evidence_refs = _build_evidence_refs(request)
    status = _preview_status(blockers)
    return _finalize_preview(
        DisableSchedulePreview,
        {
            "action": "disable_schedule",
            "review_status": status,
            "eligible_for_apply": not blockers,
            "evidence_refs": evidence_refs,
            "blockers": blockers,
            "impacts": impacts,
            "schedule_enabled_after": False,
        },
    )


def preview_clone_draft(request, *, trusted_role=None):
    request = CloneDraftPreviewRequest.model_validate(request)
    blockers = []
    impacts = []
    _common_blockers(request, blockers, trusted_role)
    if request.requested_secret_copy:
        _add_blocker(
            blockers,
            "secret_copy_unsupported",
            "Clone preview does not copy secrets from the source job.",
            [f"job:{request.snapshot.job_name}"],
        )
    if not {"names","assignments","target_vm","target_repository"} <= set(request.proof_coverage):
        _add_blocker(blockers,"missing_clone_proof","Complete names/assignments and verified target VM/repository evidence are required.",[f"job:{request.snapshot.job_name}"])
    new_name_ref = f"clone-name:{request.new_job_name}"
    existing_names = {name.casefold() for name in request.existing_job_names}
    if request.new_job_name.casefold() in existing_names or request.new_job_name.casefold() == request.snapshot.job_name.casefold():
        _add_blocker(
            blockers,
            "name_conflict",
            "Choose a unique managed job name for the clone draft.",
            [new_name_ref],
        )
    for assignment in request.existing_assignments:
        if assignment.vm_identity == request.target_vm_identity and assignment.state == "managed":
            _add_blocker(
                blockers,
                "duplicate_assignment",
                f"VM {request.target_vm_identity} is already assigned to managed job {assignment.job_name}.",
                [f"assignment:{assignment.vm_identity}:{assignment.stable_id}"],
            )
    draft_resources = _clone_resource_names(request.new_job_name)
    existing_resource_keys = {_resource_key(resource.resource_type, resource.resource_name) for resource in request.resources}
    for resource in draft_resources:
        if _resource_key(resource.resource_type, resource.resource_name) in existing_resource_keys:
            _add_blocker(
                blockers,
                "resource_name_conflict",
                f"Derived {resource.resource_type} name {resource.resource_name} already exists in the reviewed namespace.",
                [f"resource:{resource.resource_type}:{resource.resource_name}"],
            )
    _add_impact(
        impacts,
        "clone_disabled_by_default",
        "warning",
        "The clone draft keeps automatic execution disabled until a separate confirmed apply enables scheduling.",
        [new_name_ref],
    )
    _add_impact(
        impacts,
        "dedicated_resources_required",
        "obligation",
        "The clone requires its own job, FileSet, Pool and Schedule resources bound to the selected VM and repository.",
        [new_name_ref, f"repository:{request.target_repository_id}"],
    )
    _add_impact(
        impacts,
        "history_not_copied",
        "info",
        "Backup history, recovery chains and retention ownership stay with the source job.",
        [f"job:{request.snapshot.job_name}", new_name_ref],
    )
    _add_impact(
        impacts,
        "secrets_not_copied",
        "info",
        "Secrets and transport credentials are intentionally excluded from clone drafts.",
        [new_name_ref],
    )
    for dependency in request.dependencies:
        _add_impact(
            impacts,
            "dependency_review_required",
            "obligation",
            f"Dependency relationship with {dependency.related_job_name} must be reviewed separately; it is not copied into the clone draft.",
            [f"dependency:{dependency.relation}:{dependency.related_stable_id}:proof={dependency.proof_revision or 0}"],
        )
    extra_refs = [
        new_name_ref,
        f"clone-target-vm:{request.target_vm_identity}",
        f"clone-target-repository:{request.target_repository_id}",
    ] + [f"assignment:{row.vm_identity}:{row.stable_id}" for row in request.existing_assignments]
    evidence_refs = _build_evidence_refs(request, extra=extra_refs)
    status = _preview_status(blockers)
    return _finalize_preview(
        CloneDraftPreview,
        {
            "action": "clone_draft",
            "review_status": status,
            "eligible_for_apply": not blockers,
            "evidence_refs": evidence_refs,
            "blockers": blockers,
            "impacts": impacts,
            "source_stable_id": request.snapshot.stable_id,
            "new_job_name": request.new_job_name,
            "target_vm_identity": request.target_vm_identity,
            "target_repository_id": request.target_repository_id,
            "automatic_schedule": False,
            "history_copied": False,
            "secrets_copied": False,
            "draft_resources": draft_resources,
        },
    )


def preview_remove_configuration(request, *, trusted_role=None):
    request = RemoveConfigurationPreviewRequest.model_validate(request)
    blockers = []
    impacts = []
    _common_blockers(request, blockers, trusted_role)
    if not request.preserve_backup_data or request.delete_backup_data_requested:
        _add_blocker(
            blockers,
            "data_deletion_unsupported",
            "This preview only supports configuration removal while preserving existing backup data.",
            [f"job:{request.snapshot.job_name}"],
        )
    _exclusive_resource_proofs(request.resources, blockers)
    _dependency_blockers(
        request,
        blockers,
        "Job dependency {job} must be resolved before removing the managed configuration.",
    )
    retained = request.retained_recovery
    recovery_ref = (
        f"recovery:count={retained.recovery_point_count}:latest="
        + ",".join(str(job_id) for job_id in retained.latest_job_ids)
        + f":retained={int(bool(retained.retained_recovery_confirmed))}:catalog={int(bool(retained.catalog_visibility_confirmed))}:retention={int(bool(retained.retention_owner_confirmed))}:cleanup={int(bool(retained.cleanup_owner_confirmed))}:retirement={int(bool(retained.retirement_record_confirmed))}"
    )
    for confirmed, code, summary in (
        (retained.retained_recovery_confirmed, "preserved_backup_proof_missing", "Retained recovery proof is required before removing configuration."),
        (retained.catalog_visibility_confirmed, "catalog_visibility_proof_missing", "Evidence is required that retained backups remain discoverable after retirement."),
        (retained.retention_owner_confirmed, "retention_owner_proof_missing", "Retention ownership must be identified before configuration removal."),
        (retained.cleanup_owner_confirmed, "cleanup_owner_proof_missing", "Cleanup ownership must be identified before configuration removal."),
        (retained.retirement_record_confirmed, "retirement_record_proof_missing", "A managed retirement record is required to keep retained backups attributable."),
    ):
        if confirmed is not True:
            _add_blocker(blockers, code, summary, [recovery_ref])
    retained_obligations = [
        "Retained recovery points must stay discoverable through a managed retirement record.",
        "Retention and cleanup ownership must remain explicit after config removal.",
        "Shared or external resources must not be deleted implicitly.",
    ]
    _add_impact(
        impacts,
        "backups_preserved",
        "warning",
        "Removing configuration keeps backup data and recovery chains in place by default.",
        [recovery_ref],
    )
    _add_impact(
        impacts,
        "retention_review_required",
        "obligation",
        "Retained recovery points need explicit catalog, retention and cleanup ownership after job retirement.",
        [recovery_ref],
    )
    _add_impact(
        impacts,
        "shared_resources_retained",
        "obligation",
        "Shared repositories, schedules, pools or mappings require their own verified follow-up handling.",
        [f"job:{request.snapshot.job_name}"],
    )
    evidence_refs = _build_evidence_refs(request, extra=[recovery_ref])
    status = _preview_status(blockers)
    return _finalize_preview(
        RemoveConfigurationPreview,
        {
            "action": "remove_configuration",
            "review_status": status,
            "eligible_for_apply": not blockers,
            "evidence_refs": evidence_refs,
            "blockers": blockers,
            "impacts": impacts,
            "preserve_backup_data": True,
            "delete_backup_data_supported": False,
            "retained_recovery_job_ids": retained.latest_job_ids,
            "retained_obligations": retained_obligations,
        },
    )
