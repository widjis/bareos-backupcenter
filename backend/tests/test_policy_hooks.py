import pytest

from integration.policy_hooks import verify_dependency_hooks

SOURCE = "VMware-MTIMRWKF01"
OTHER = "VMware-MTIMRWCNTDEV"
TARGET = "VMware-PNET"


def reviewed_definition(automatic=True, trigger_mode="after_job"):
    return {
        "automatic": automatic,
        "trigger_mode": trigger_mode,
        "after_job": {
            "source_job": SOURCE,
            "on_failure": "run_anyway",
            "level": "incremental",
        },
        "time_wita": "22:15",
        "window_end_wita": "23:30",
    }


def hook_block(level="incremental", start="22:15", end="23:30"):
    command = (
        "/opt/bareos-api-venv/bin/python "
        "/opt/bareos/25.1.1/lib/bareos/scripts/backupcenter-after-job.py "
        f"--target {TARGET} --level {level} --window-start {start} --window-end {end}"
    )
    return (
        f"# BackupCenter dependency trigger begin: {TARGET}\n"
        f' Run After Job = "{command}"\n'
        f' Run After Failed Job = "{command}"\n'
        f"# BackupCenter dependency trigger end: {TARGET}\n"
    )


def managed_jobs(source_text="", other_text=""):
    jobs = {
        "VMware-PNET": "Job {\n Name = VMware-PNET\n}\n",
        "VMware-MTIMRWKF01": f"Job {{\n Name = {SOURCE}\n{source_text}}}\n",
        "VMware-MTIMRWCNTDEV": f"Job {{\n Name = {OTHER}\n{other_text}}}\n",
    }
    return jobs


def test_verify_dependency_hooks_accepts_exact_selected_source_block():
    verify_dependency_hooks(
        managed_jobs(source_text=hook_block()),
        TARGET,
        reviewed_definition(),
        hook_block(),
    )


def test_verify_dependency_hooks_rejects_block_on_wrong_source():
    with pytest.raises(ValueError, match="instead of"):
        verify_dependency_hooks(
            managed_jobs(other_text=hook_block()),
            TARGET,
            reviewed_definition(),
            hook_block(),
        )


def test_verify_dependency_hooks_rejects_stale_duplicate_blocks():
    with pytest.raises(ValueError, match="duplicated"):
        verify_dependency_hooks(
            managed_jobs(source_text=hook_block(), other_text=hook_block()),
            TARGET,
            reviewed_definition(),
            hook_block(),
        )


def test_verify_dependency_hooks_rejects_wrong_hook_arguments():
    with pytest.raises(ValueError, match="reviewed hook"):
        verify_dependency_hooks(
            managed_jobs(source_text=hook_block(level="full")),
            TARGET,
            reviewed_definition(),
            hook_block(),
        )


def test_verify_dependency_hooks_rejects_orphan_marker_pairs():
    orphan = (
        f"# BackupCenter dependency trigger begin: {TARGET}\n"
        ' Run After Job = "stale"\n'
    )
    with pytest.raises(ValueError, match="malformed"):
        verify_dependency_hooks(
            managed_jobs(source_text=orphan),
            TARGET,
            reviewed_definition(),
            hook_block(),
        )


def test_verify_dependency_hooks_rejects_disabled_after_job_markers():
    with pytest.raises(ValueError, match="must be absent"):
        verify_dependency_hooks(
            managed_jobs(source_text=hook_block()),
            TARGET,
            reviewed_definition(automatic=False),
            hook_block(),
        )


def test_verify_dependency_hooks_accepts_calendar_definition_without_markers():
    verify_dependency_hooks(
        managed_jobs(),
        TARGET,
        reviewed_definition(trigger_mode="calendar"),
        hook_block(),
    )


def test_unmarked_target_command_cannot_hide_outside_reviewed_block():
    jobs=managed_jobs(source_text=hook_block())
    jobs[OTHER] += f' Run After Job = "python trigger --target {TARGET}"\n'
    with pytest.raises(ValueError,match="Unmanaged target hook"):
        verify_dependency_hooks(jobs,TARGET,reviewed_definition(),hook_block())

def test_indented_orphan_marker_is_rejected():
    jobs=managed_jobs(source_text=hook_block())
    jobs[OTHER] += f'  # BackupCenter dependency trigger begin: {TARGET}\n'
    with pytest.raises(ValueError,match="malformed"):
        verify_dependency_hooks(jobs,TARGET,reviewed_definition(),hook_block())
