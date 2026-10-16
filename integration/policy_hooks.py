"""Verify only BackupCenter-managed dependency hook marker blocks.

This boundary is intentionally narrow: it trusts only the exact begin/end block
shape emitted by integration.apply_backup_policy.dependency_block(). It does
not parse arbitrary Bareos directives as authoritative proof of runtime hooks.
"""
from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _scan_target_blocks(text: str, target: str) -> tuple[list[str], bool]:
    begin = f"# BackupCenter dependency trigger begin: {target}"
    end = f"# BackupCenter dependency trigger end: {target}"
    blocks: list[str] = []
    current: list[str] | None = None
    malformed = False
    for line in _normalize(text).splitlines(keepends=True):
        marker = line.rstrip("\n")
        if marker.strip() in (begin, end) and marker != marker.strip():
            malformed = True
        if marker == begin:
            malformed = malformed or current is not None
            current = [line]
            continue
        if marker == end:
            if current is None:
                malformed = True
            else:
                current.append(line)
                blocks.append("".join(current))
                current = None
            continue
        if current is not None:
            current.append(line)
    return blocks, malformed or current is not None


def verify_dependency_hooks(
    jobs: dict[str, str], target: str, definition: dict, expected_block: str
) -> None:
    scans = {job: _scan_target_blocks(text, target) for job, text in jobs.items()}
    bad = sorted(job for job, (_, malformed) in scans.items() if malformed)
    if bad:
        raise ValueError(
            f"Dependency hook markers for {target} are malformed on {', '.join(bad)}."
        )
    for job, (found, _) in scans.items():
        remainder = _normalize(jobs[job])
        for block in found:
            remainder = remainder.replace(block, "", 1)
        if re.search(r"--target\s+" + re.escape(target) + r"(?![A-Za-z0-9_.-])", remainder):
            raise ValueError(f"Unmanaged target hook for {target} on {job} requires inspection.")
    blocks = {job: found for job, (found, _) in scans.items() if found}
    wants_hook = (
        definition.get("trigger_mode") == "after_job" and definition.get("automatic")
    )
    if not wants_hook:
        if blocks:
            raise ValueError(
                f"Dependency hook markers for {target} must be absent but were found on "
                f"{', '.join(sorted(blocks))}."
            )
        return
    source = (definition.get("after_job") or {}).get("source_job")
    if source not in jobs:
        raise ValueError(f"Selected after-job source for {target} is outside managed jobs.")
    source_blocks = blocks.get(source, [])
    others = sorted(job for job in blocks if job != source)
    if others and not source_blocks:
        raise ValueError(
            f"Dependency hook for {target} is attached to {', '.join(others)} instead of {source}."
        )
    if others:
        raise ValueError(
            f"Dependency hook for {target} is duplicated on {source} and {', '.join(others)}."
        )
    if len(source_blocks) != 1:
        raise ValueError(
            f"Expected exactly one managed dependency hook block for {target} on {source}."
        )
    if _normalize(source_blocks[0]) != _normalize(expected_block):
        raise ValueError(
            f"Dependency hook block for {target} on {source} does not match the reviewed hook."
        )
