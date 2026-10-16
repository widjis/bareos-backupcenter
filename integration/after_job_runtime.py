from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

SAFE_JOB = re.compile(r"^VMware-[A-Z0-9][A-Z0-9-]{0,63}$")
SAFE_LEVELS = {"configured", "full", "incremental"}
ACTIVE_SQL = (
    "SELECT count(*) FROM job WHERE name='{name}' AND jobstatus = ANY("
    "string_to_array('R,C,B,F,S,M,s,m,j,c,d,t,p,q,a,i,L', ','));"
)
DEFAULT_STATE_DIR = Path(
    os.environ.get("BACKUPCENTER_AFTER_JOB_STATE", "/var/lib/bareos-after-job-runtime")
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def validate_job(name: str, field: str) -> str:
    require(bool(SAFE_JOB.fullmatch(name)), f"{field} must match {SAFE_JOB.pattern}.")
    return name


def parse_hhmm(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    require(bool(match), "Time must use HH:MM.")
    return int(match.group(1)), int(match.group(2))


def minute_of_day(value: str) -> int:
    hour, minute = parse_hhmm(value)
    return hour * 60 + minute


def now_wita() -> datetime:
    return datetime.now(ZoneInfo("Asia/Makassar"))


def durable_key(source: str, source_job_id: int, target: str) -> str:
    raw = f"{source}\0{source_job_id}\0{target}".encode()
    return hashlib.sha256(raw).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        flag = getattr(os, "O_DIRECTORY", None)
        if flag is not None:
            directory = os.open(path.parent, flag)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_json(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def native_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = open(path, "a+", encoding="utf-8")
    try:
        import fcntl  # type: ignore

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except ModuleNotFoundError as exc:
        handle.close()
        raise RuntimeError("fcntl is unavailable; inject a lock factory for this platform.") from exc
    try:
        yield
    finally:
        handle.close()


def receipt_paths(state_dir: Path, key: str) -> tuple[Path, Path]:
    return state_dir / "receipts" / f"{key}.json", state_dir / "locks" / f"{key}.lock"


def target_lock_path(state_dir: Path, target: str) -> Path:
    return state_dir / "locks" / f"{target}.target.lock"


def pending_for_target(state_dir: Path, target: str, key: str, query_terminal) -> dict | None:
    for path in (state_dir / "receipts").glob("*.json"):
        row = read_json(path)
        if row and row.get("target") == target and row.get("key") != key:
            if row.get("state") == "Queued" and query_terminal(row):
                transition(path, row, "Completed")
                continue
            if row.get("state") in {"Dispatching", "Queued", "Unknown"}:
                return row
    return None


def window_state(start: str, end: str | None, current: datetime) -> str:
    current_minute = current.hour * 60 + current.minute
    start_minute = minute_of_day(start)
    end_minute = minute_of_day(end or "23:59")
    require(end_minute >= start_minute, "Window end must not be earlier than window start.")
    if current_minute < start_minute:
        return "before"
    if current_minute > end_minute:
        return "after"
    return "open"


def query_active_target(target: str, *, psql: str = "psql") -> bool:
    sql = ACTIVE_SQL.format(name=target.replace("'", "''"))
    result = subprocess.run(
        [psql, "-X", "-At", "-d", "bareos", "-c", sql],
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Active-target SQL query failed.")
    count = result.stdout.strip()
    require(bool(re.fullmatch(r"\d+", count)), "Active-target SQL did not return a valid count.")
    return int(count) > 0


def query_terminal_receipt(row: dict) -> bool:
    job_id = row.get("queuedJobId")
    require(type(job_id) is int and job_id > 0, "Queued receipt lacks a valid JobId.")
    result = subprocess.run(["psql", "-X", "-At", "-d", "bareos", "-c",
        f"SELECT name,jobstatus FROM job WHERE jobid={job_id};"], text=True, capture_output=True, timeout=30)
    require(result.returncode == 0, "Queued-job SQL lookup failed.")
    value = result.stdout.strip().split("|")
    require(len(value) == 2 and value[0] == row["target"], "Queued JobId identity could not be reconciled.")
    return value[1] in {"T", "W", "E", "e", "f", "A", "I"}


def run_bconsole(target: str, level: str, *, bconsole: str | None = None) -> subprocess.CompletedProcess[str]:
    binary = bconsole or "/opt/bareos/25.1.1/sbin/bconsole"
    command = f"run job={target} yes" if level == "configured" else f"run job={target} level={level.title()} yes"
    return subprocess.run([binary], input=command + "\nquit\n", text=True, capture_output=True, timeout=30)


def parse_ack(transcript: str) -> int:
    ids = {int(value) for value in re.findall(r"\bJobId\s*=\s*(\d+)\b", transcript, re.I) if int(value) > 0}
    if re.search(r"(?i)\b(error|fatal|denied|rejected|unknown command)\b", transcript):
        raise ValueError("bconsole transcript contains an error.")
    require(bool(ids) and bool(re.search(r"\bJob queued\b", transcript, re.I)), "bconsole transcript did not acknowledge a queued JobId.")
    require(len(ids) == 1, "bconsole transcript is ambiguous.")
    return next(iter(ids))


def transition(receipt_path: Path, base: dict, state: str, **extra) -> dict:
    row = {**base, "state": state, "updatedAt": now_wita().isoformat(timespec="seconds"), **extra}
    atomic_json(receipt_path, row)
    return row


def trigger(
    source: str,
    source_job_id: int,
    target: str,
    level: str,
    window_start: str,
    window_end: str | None = None,
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    now: Callable[[], datetime] = now_wita,
    query_active: Callable[[str], bool] = query_active_target,
    run_console: Callable[[str, str], object] = run_bconsole,
    lock_factory: Callable[[Path], contextlib.AbstractContextManager] | None = None,
    after_dispatch: Callable[[], None] | None = None,
    query_terminal: Callable[[dict], bool] = query_terminal_receipt,
) -> dict:
    source = validate_job(source, "source")
    target = validate_job(target, "target")
    require(source != target, "source and target must differ.")
    require(type(source_job_id) is int and source_job_id > 0, "source_job_id must be positive.")
    require(level in SAFE_LEVELS, "level is invalid.")
    parse_hhmm(window_start)
    if window_end:
        parse_hhmm(window_end)
    state_dir = Path(state_dir)
    key = durable_key(source, source_job_id, target)
    receipt_path, dedup_lock = receipt_paths(state_dir, key)
    lock = lock_factory or (lambda path: contextlib.contextmanager(native_lock)(path))
    with lock(target_lock_path(state_dir, target)):
        with lock(dedup_lock):
            existing = read_json(receipt_path)
            if existing:
                require((existing.get("level"), existing.get("windowStart"), existing.get("windowEnd")) == (level, window_start, window_end), "Existing source-run receipt has a different reviewed intent.")
            if existing and existing.get("state") in {"Dispatching", "Queued", "Rejected", "Expired", "Unknown", "Blocked", "Completed"}:
                return existing
            base = existing or {
                "key": key,
                "source": source,
                "sourceJobId": source_job_id,
                "target": target,
                "level": level,
                "windowStart": window_start,
                "windowEnd": window_end,
                "state": "Prepared",
                "createdAt": now().isoformat(timespec="seconds"),
                "windowDate": now().date().isoformat(),
                "attempts": 0,
            }
            if base.get("windowDate") != now().date().isoformat():
                return transition(receipt_path, base, "Expired", expiredReason="window_date_passed")
            phase = window_state(window_start, window_end, now())
            if phase == "before":
                return transition(receipt_path, base, "Deferred", deferredReason="before_window")
            if phase == "after":
                return transition(receipt_path, base, "Expired", expiredReason="window_closed")
            other = pending_for_target(state_dir, target, key, query_terminal)
            if other:
                return transition(receipt_path, base, "Deferred", deferredReason="target_pending", blockingKey=other["key"])
            if query_active(target):
                return transition(receipt_path, base, "Deferred", deferredReason="active_target")
            dispatching = transition(receipt_path, {**base, "attempts": int(base.get("attempts", 0)) + 1}, "Dispatching")
            try:
                result = run_console(target, level)
                if after_dispatch:
                    after_dispatch()
                transcript = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
                require(getattr(result, "returncode", 0) == 0, "bconsole process did not complete successfully.")
                queued_job_id = parse_ack(transcript)
                return transition(receipt_path, dispatching, "Queued", queuedJobId=queued_job_id)
            except ValueError as exc:
                return transition(receipt_path, dispatching, "Unknown", message=str(exc)[:200])
            except Exception as exc:
                return transition(receipt_path, dispatching, "Unknown", message=str(exc)[:200])


def drain(
    *,
    state_dir: Path = DEFAULT_STATE_DIR,
    now: Callable[[], datetime] = now_wita,
    query_active: Callable[[str], bool] = query_active_target,
    run_console: Callable[[str, str], object] = run_bconsole,
    lock_factory: Callable[[Path], contextlib.AbstractContextManager] | None = None,
    target: str | None = None,
    query_terminal: Callable[[dict], bool] = query_terminal_receipt,
) -> list[dict]:
    if target:
        validate_job(target, "target")
    rows = []
    for path in sorted((Path(state_dir) / "receipts").glob("*.json")):
        row = read_json(path)
        if not row or row.get("state") != "Deferred":
            continue
        if target and row.get("target") != target:
            continue
        rows.append(
            trigger(
                row["source"],
                int(row["sourceJobId"]),
                row["target"],
                row["level"],
                row["windowStart"],
                row.get("windowEnd"),
                state_dir=Path(state_dir),
                now=now,
                query_active=query_active,
                run_console=run_console,
                lock_factory=lock_factory,
                query_terminal=query_terminal,
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain", action="store_true")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--source")
    parser.add_argument("--source-job-id", type=int)
    parser.add_argument("--target")
    parser.add_argument("--level", default="configured")
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.drain:
            result = drain(state_dir=Path(args.state_dir), target=args.target)
        else:
            require(all([args.source, args.source_job_id, args.target, args.window_start]), "--source, --source-job-id, --target, and --window-start are required.")
            result = trigger(
                args.source,
                args.source_job_id,
                args.target,
                args.level,
                args.window_start,
                args.window_end,
                state_dir=Path(args.state_dir),
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:200]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
