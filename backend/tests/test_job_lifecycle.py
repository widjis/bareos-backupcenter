from uuid import UUID
import pytest
from pydantic import ValidationError
from backend.job_lifecycle import CloneDraftPreviewRequest, DisableSchedulePreviewRequest, ManagedTargetSnapshot, OperationEvidence, RemoveConfigurationPreviewRequest, ResourceUsageEvidence, RetainedRecoveryEvidence, UnresolvedIntentEvidence, VmAssignmentEvidence, preview_clone_draft as _preview_clone_draft, preview_disable_schedule as _preview_disable_schedule, preview_remove_configuration as _preview_remove_configuration
VM_A = UUID('11111111-1111-1111-1111-111111111111')
VM_B = UUID('22222222-2222-2222-2222-222222222222')

def snapshot(**kw):
    return ManagedTargetSnapshot(**{'stable_id': 'managed.pnet', 'job_name': 'Managed PNET', 'selection_revision': 7, 'snapshot_revision': 7, 'identity_revision': 3, 'managed_vm_ids': [VM_A], 'repository_id': 'repo-primary'} | kw)

def schedule_resource(**kw):
    return ResourceUsageEvidence(**{'resource_type': 'schedule', 'resource_name': 'managed-pnet.schedule', 'ownership': 'exclusive', 'usage_count': 1, 'proof_revision': 9} | kw)

def exclusive_resource(resource_type, resource_name, **kw):
    return ResourceUsageEvidence(**{'resource_type': resource_type, 'resource_name': resource_name, 'ownership': 'exclusive', 'usage_count': 1, 'proof_revision': 9} | kw)

def retained_recovery(**kw):
    return RetainedRecoveryEvidence(**{'recovery_point_count': 2, 'latest_job_ids': [23, 24], 'retained_recovery_confirmed': True, 'catalog_visibility_confirmed': True, 'retention_owner_confirmed': True, 'cleanup_owner_confirmed': True, 'retirement_record_confirmed': True} | kw)

def test_disable_schedule_denies_non_admin_review():
    result = preview_disable_schedule(DisableSchedulePreviewRequest(actor_role='Backup Operator', snapshot=snapshot(), resources=[schedule_resource()]))
    assert not result.eligible_for_apply
    assert result.review_status == 'blocked'
    assert {item.code for item in result.blockers} == {'permission_denied'}

def test_disable_schedule_blocks_active_jobs_and_dependencies():
    result = preview_disable_schedule({'actor_role': 'Admin', 'snapshot': snapshot().model_dump(), 'resources': [schedule_resource().model_dump()], 'operations': [OperationEvidence(operation_id='op-100', kind='backup', state='active', summary='Running backup').model_dump()], 'dependencies': [{'relation': 'required_by', 'related_stable_id': 'managed.child', 'related_job_name': 'Managed Child', 'proof_revision': 11}]})
    codes = {item.code for item in result.blockers}
    assert 'pending_operation' in codes
    assert 'dependency_blocker' in codes

def test_multi_vm_jobs_are_explicitly_unsupported():
    result = preview_disable_schedule({'actor_role': 'Admin', 'snapshot': snapshot(managed_vm_ids=[VM_A, VM_B]).model_dump(), 'resources': [schedule_resource().model_dump()]})
    assert 'unsupported_multi_vm' in {item.code for item in result.blockers}

def test_clone_preview_rejects_unsafe_name_contract():
    with pytest.raises(ValidationError):
        CloneDraftPreviewRequest(actor_role='Admin', snapshot=snapshot(), new_job_name='../prod', target_vm_identity=VM_B, target_repository_id='repo-clone')

def test_clone_preview_detects_name_conflict_and_duplicate_assignment():
    result = preview_clone_draft(CloneDraftPreviewRequest(actor_role='Admin', snapshot=snapshot(), new_job_name='Managed PNET', target_vm_identity=VM_B, target_repository_id='repo-clone', existing_job_names=['Managed PNET', 'Another Job'], existing_assignments=[VmAssignmentEvidence(vm_identity=VM_B, stable_id='managed.other', job_name='Other Managed Job')]))
    codes = {item.code for item in result.blockers}
    assert 'name_conflict' in codes
    assert 'duplicate_assignment' in codes
    assert result.automatic_schedule is False
    assert result.secrets_copied is False

def test_clone_preview_digest_changes_with_reviewed_evidence():
    base = preview_clone_draft({'actor_role': 'Admin', 'snapshot': snapshot().model_dump(), 'new_job_name': 'Managed Clone One', 'target_vm_identity': str(VM_B), 'target_repository_id': 'repo-clone', 'existing_job_names': ['Managed PNET']})
    changed = preview_clone_draft({'actor_role': 'Admin', 'snapshot': snapshot(snapshot_revision=8, selection_revision=8).model_dump(), 'new_job_name': 'Managed Clone One', 'target_vm_identity': str(VM_B), 'target_repository_id': 'repo-clone', 'existing_job_names': ['Managed PNET']})
    assert base.review_digest != changed.review_digest

def test_clone_preview_blocks_secret_copy_and_resource_conflicts():
    result = preview_clone_draft({'actor_role': 'Admin', 'snapshot': snapshot().model_dump(), 'new_job_name': 'Managed Clone Two', 'target_vm_identity': str(VM_B), 'target_repository_id': 'repo-clone', 'requested_secret_copy': True, 'resources': [exclusive_resource('job', 'Managed-Clone-Two').model_dump(), exclusive_resource('fileset', 'Managed-Clone-Two.fileset').model_dump()]})
    codes = {item.code for item in result.blockers}
    assert 'secret_copy_unsupported' in codes
    assert 'resource_name_conflict' in codes

def test_remove_configuration_blocks_stale_revision_shared_resources_and_missing_proof():
    result = preview_remove_configuration(RemoveConfigurationPreviewRequest(actor_role='Admin', snapshot=snapshot(selection_revision=6, snapshot_revision=7), resources=[ResourceUsageEvidence(resource_type='pool', resource_name='managed-pnet.pool', ownership='shared', usage_count=2, proof_revision=12), ResourceUsageEvidence(resource_type='retention_mapping', resource_name='retention-map', ownership='unknown', usage_count=1, proof_revision=None)], operations=[OperationEvidence(operation_id='cleanup-1', kind='cleanup', state='waiting', summary='Retention cleanup queued')], unresolved_intents=[UnresolvedIntentEvidence(kind='move_repository', summary='Repository move already under review')], retained_recovery=retained_recovery(retained_recovery_confirmed=None, catalog_visibility_confirmed=None, retirement_record_confirmed=None)))
    codes = {item.code for item in result.blockers}
    assert 'stale_snapshot' in codes
    assert 'shared_resource' in codes
    assert 'missing_resource_proof' in codes
    assert 'pending_operation' in codes
    assert 'unresolved_intent' in codes
    assert 'preserved_backup_proof_missing' in codes
    assert 'catalog_visibility_proof_missing' in codes
    assert 'retirement_record_proof_missing' in codes

def test_remove_configuration_defaults_to_preserved_backups_with_obligations():
    result = preview_remove_configuration({'actor_role': 'Admin', 'snapshot': snapshot().model_dump(), 'resources': [exclusive_resource('job', 'Managed-PNET').model_dump(), schedule_resource().model_dump(), exclusive_resource('fileset', 'Managed-PNET.fileset').model_dump()], 'retained_recovery': retained_recovery().model_dump()})
    assert result.eligible_for_apply
    assert result.preserve_backup_data is True
    assert result.delete_backup_data_supported is False
    assert result.retained_recovery_job_ids == [23, 24]
    assert any(('discoverable' in item for item in result.retained_obligations))


# These wrappers simulate trusted server-side adapters for the original fixtures.
# Untrusted callers are exercised against the direct planner functions below.
def _trusted_fixture(request):
    data=request.model_dump() if hasattr(request,"model_dump") else dict(request)
    data={**data,"proof_revision":data["snapshot"]["snapshot_revision"],"proof_coverage":["operations","dependencies","intents","resources","names","assignments","target_vm","target_repository"]}
    return data

def preview_disable_schedule(request):
    data=_trusted_fixture(request)
    return _preview_disable_schedule(data,trusted_role=data["actor_role"])

def preview_clone_draft(request):
    data=_trusted_fixture(request)
    return _preview_clone_draft(data,trusted_role=data["actor_role"])

def preview_remove_configuration(request):
    data=_trusted_fixture(request)
    return _preview_remove_configuration(data,trusted_role=data["actor_role"])


def test_missing_registry_coverage_fails_closed_and_role_is_trusted_separately():
    data={"actor_role":"Admin","snapshot":snapshot().model_dump(),"resources":[schedule_resource().model_dump()]}
    result=_preview_disable_schedule(data,trusted_role="Viewer")
    assert {b.code for b in result.blockers}>={"permission_denied","missing_registry_proof"}
    result=_preview_disable_schedule(data)
    assert "permission_denied" in {b.code for b in result.blockers}


def test_clone_unknown_target_and_empty_registry_are_not_safe_defaults():
    data={"actor_role":"Admin","snapshot":snapshot().model_dump(),"new_job_name":"Unverified Clone","target_vm_identity":VM_B,"target_repository_id":"unverified"}
    result=_preview_clone_draft(data,trusted_role="Admin")
    assert not result.eligible_for_apply
    assert {b.code for b in result.blockers}>={"missing_registry_proof","missing_clone_proof"}


def test_large_evidence_is_bounded_but_digest_still_covers_omitted_refs():
    resources=[exclusive_resource("pool",f"pool-{i:02d}").model_dump() for i in range(31)]+[schedule_resource().model_dump()]
    data={"actor_role":"Admin","snapshot":snapshot().model_dump(),"resources":resources}
    a=preview_disable_schedule(data)
    changed=[dict(row) for row in resources];changed[30]["proof_revision"]=10
    b=preview_disable_schedule({**data,"resources":changed})
    assert len(a.evidence_refs)<=32 and a.review_digest!=b.review_digest
