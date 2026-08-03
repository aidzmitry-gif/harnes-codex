#!/usr/bin/env python3
"""Portable, evidence-based acceptance gate for an agent work item.

Criteria live in .harness/acceptance/<work-item>.json. Command criteria are re-run
on every ``check``; manual criteria require both an explicit pass and evidence.
Only use commands from a profile maintained by a trusted project owner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath


SENSITIVE_DIRECTORIES = {".ssh", "credential", "credentials", "secret", "secrets"}
SENSITIVE_FILE_PATTERNS = (
    ".env*", "*.key", "*.pem", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
    "credentials.json", "credentials-*.json", "*_credentials.json", "service-account*.json",
    "secret.json", "secrets.json",
)


def root() -> Path:
    return Path(__file__).resolve().parent


def gate_path(work_item: str) -> Path:
    if not work_item.replace("-", "").replace("_", "").isalnum():
        raise ValueError("work item may contain only letters, digits, '-' and '_'")
    return root() / ".harness" / "acceptance" / f"{work_item}.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["schemaVersion"] = 2
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(data: dict) -> list[dict]:
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("gate must contain a non-empty 'criteria' array")
    seen: set[str] = set()
    for criterion in criteria:
        cid = criterion.get("id")
        kind = criterion.get("kind")
        if not isinstance(cid, str) or not cid or cid in seen:
            raise ValueError("each criterion needs a unique non-empty id")
        if kind not in ("command", "manual"):
            raise ValueError(f"{cid}: kind must be 'command' or 'manual'")
        if kind == "command" and (not isinstance(criterion.get("command"), str) or not criterion["command"].strip()):
            raise ValueError(f"{cid}: command criterion needs a non-empty command")
        timeout = criterion.get("timeoutSeconds", 600)
        if kind == "command" and (not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 600):
            raise ValueError(f"{cid}: timeoutSeconds must be an integer from 1 to 600")
        seen.add(cid)
    return criteria


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def excluded(relative: PurePosixPath) -> bool:
    parts = tuple(part.lower() for part in relative.parts)
    name = parts[-1] if parts else ""
    return (
        any(part in {".git", ".worktrees", "graphify-out", "__pycache__"} | SENSITIVE_DIRECTORIES for part in parts)
        or (len(parts) >= 2 and parts[:2] == (".harness", "acceptance"))
        or (len(parts) >= 2 and parts[:2] == (".harness", "work") and not name.endswith(".passport.json"))
        or (len(parts) >= 2 and parts[:2] == (".harness", "metrics"))
        or (len(parts) >= 3 and parts[:3] == (".harness", "benchmarks", "runs"))
        or name.endswith(".pyc")
        or any(fnmatch(name, pattern) for pattern in SENSITIVE_FILE_PATTERNS)
    )


def digest_files(base: Path, names: list[str]) -> str:
    digest = hashlib.sha256()
    base_resolved = base.resolve()
    for name in sorted(names):
        relative = PurePosixPath(name)
        if excluded(relative):
            continue
        path = base.joinpath(*relative.parts)
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"SYMLINK")
            continue
        if not path.exists():
            digest.update(b"MISSING")
            continue
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(base_resolved) or not resolved.is_file():
            digest.update(b"UNSAFE")
            continue
        digest.update(hashlib.sha256(resolved.read_bytes()).digest())
    return digest.hexdigest()


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout


def non_git_fingerprint() -> dict[str, str]:
    try:
        files = [path.relative_to(root()).as_posix() for path in root().rglob("*") if path.is_file()]
        return {"algorithm": "sha256", "value": digest_files(root(), files), "status": "ok"}
    except OSError:
        return {"algorithm": "sha256", "value": "", "status": "unavailable"}


def fingerprint() -> dict[str, str]:
    """Return a deterministic safe project-state fingerprint, or explicit unavailability."""
    try:
        git_output("rev-parse", "--is-inside-work-tree")
        index_digest = hashlib.sha256()
        for row in git_output("ls-files", "-s", "-z").split("\0"):
            if not row or "\t" not in row:
                continue
            metadata, name = row.split("\t", 1)
            if excluded(PurePosixPath(name)):
                continue
            index_digest.update(metadata.encode("utf-8"))
            index_digest.update(b"\t")
            index_digest.update(name.encode("utf-8"))
            index_digest.update(b"\0")
        changed = [name for name in git_output("diff", "--name-only", "-z").split("\0") if name and not excluded(PurePosixPath(name))]
        untracked = [name for name in git_output("ls-files", "--others", "--exclude-standard", "-z").split("\0") if name and not excluded(PurePosixPath(name))]
        payload = json.dumps({
            "index": index_digest.hexdigest(),
            "worktree": digest_files(root(), changed),
            "untracked": digest_files(root(), untracked),
        }, sort_keys=True)
        return {"algorithm": "sha256", "value": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "status": "ok"}
    except (OSError, subprocess.SubprocessError):
        if (root() / ".git").exists():
            return {"algorithm": "sha256", "value": "", "status": "unavailable"}
        return non_git_fingerprint()


def init(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if target.exists():
        print(f"FAIL gate already exists: {target}", file=sys.stderr)
        return 2
    template = load(Path(args.from_file))
    criteria = validate(template)
    for criterion in criteria:
        criterion["passes"] = False
        criterion["evidence"] = ""
    template["workItem"] = args.work_item
    save(target, template)
    print(f"PASS created {target} with {len(criteria)} criteria")
    return 0


def prove(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if not target.exists():
        print("FAIL gate does not exist", file=sys.stderr)
        return 2
    data = load(target)
    criteria = validate(data)
    for criterion in criteria:
        if criterion["id"] == args.criterion:
            if criterion["kind"] != "manual":
                print("FAIL only manual criteria can be proven manually", file=sys.stderr)
                return 2
            criterion["passes"] = True
            criterion["evidence"] = args.evidence.strip()
            if not criterion["evidence"]:
                print("FAIL evidence must not be empty", file=sys.stderr)
                return 2
            criterion["checkedAt"] = now_utc()
            criterion["durationMs"] = 0
            criterion["fingerprint"] = fingerprint()
            save(target, data)
            print(f"PASS recorded evidence for {args.criterion}")
            return 0
    print("FAIL criterion does not exist", file=sys.stderr)
    return 2


def evaluate(criterion: dict) -> tuple[bool, str]:
    if criterion["kind"] == "manual":
        evidence = str(criterion.get("evidence", "")).strip()
        stored = criterion.get("fingerprint")
        if not evidence:
            return False, "missing manual evidence"
        if not isinstance(stored, dict):
            return False, "stale manual evidence: re-prove required"
        current = fingerprint()
        if stored.get("status") != "ok" or current.get("status") != "ok" or stored != current:
            return False, "stale manual evidence: re-prove required"
        return bool(criterion.get("passes")), "manual evidence"
    started = time.monotonic()
    criterion["checkedAt"] = now_utc()
    criterion["fingerprint"] = fingerprint()
    try:
        result = subprocess.run(
            criterion["command"], shell=True, cwd=root(), capture_output=True,
            text=True, timeout=criterion.get("timeoutSeconds", 600), encoding="utf-8", errors="replace",
        )
        criterion["passes"] = result.returncode == 0
        output = (result.stdout or result.stderr).strip().splitlines()
        criterion["evidence"] = f"auto: exit {result.returncode}; {output[-1][:160] if output else 'no output'}"
    except subprocess.TimeoutExpired:
        criterion["passes"] = False
        criterion["evidence"] = f"auto: timeout after {criterion.get('timeoutSeconds', 600)} seconds"
    criterion["durationMs"] = max(0, round((time.monotonic() - started) * 1000))
    return criterion["passes"], criterion["evidence"]


def check(args: argparse.Namespace) -> int:
    target = gate_path(args.work_item)
    if not target.exists():
        print("FAIL gate does not exist", file=sys.stderr)
        return 2
    try:
        data = load(target)
        criteria = validate(data)
        results = [(criterion["id"], *evaluate(criterion)) for criterion in criteria]
        save(target, data)
    except (ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL invalid or uncheckable gate: {exc}", file=sys.stderr)
        return 2
    for cid, passed, note in results:
        print(f"{'PASS' if passed else 'FAIL'} {cid}: {note}")
    return 0 if all(passed for _, passed, _ in results) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence-based acceptance gate")
    sub = parser.add_subparsers(dest="action", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("work_item")
    p_init.add_argument("--from", dest="from_file", required=True)
    p_init.set_defaults(func=init)
    p_prove = sub.add_parser("prove")
    p_prove.add_argument("work_item")
    p_prove.add_argument("criterion")
    p_prove.add_argument("--evidence", required=True)
    p_prove.set_defaults(func=prove)
    p_check = sub.add_parser("check")
    p_check.add_argument("work_item")
    p_check.set_defaults(func=check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
