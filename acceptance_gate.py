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
from pathlib import Path, PurePosixPath, PureWindowsPath


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
        if not isinstance(criterion, dict):
            raise ValueError("each criterion must be an object")
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
        if kind == "command" and "expect" in criterion:
            expect = criterion["expect"]
            if not isinstance(expect, str) or not expect.strip() or len(expect.encode("utf-8")) > 1024:
                raise ValueError(f"{cid}: expect must be a non-empty literal marker no larger than 1024 UTF-8 bytes")
        if kind == "command" and "cwd" in criterion:
            validate_cwd(criterion["cwd"])
        seen.add(cid)
    return criteria


def validate_cwd(value: object) -> str:
    """Accept only normalized repository-relative working directories."""
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("cwd must be a non-empty repository-relative POSIX path")
    if value == ".":
        return value
    windows_path = PureWindowsPath(value)
    parts = value.split("/")
    if windows_path.drive or windows_path.root or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("cwd must stay within the repository and use normalized path segments")
    return value


def resolve_cwd(value: object = None) -> Path:
    """Resolve a declared cwd and refuse paths outside the repository root."""
    base = root().resolve()
    relative = "." if value is None else validate_cwd(value)
    candidate = base if relative == "." else base.joinpath(*PurePosixPath(relative).parts)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir() or not resolved.is_relative_to(base):
        raise ValueError("cwd must resolve to a directory inside the repository")
    return resolved


def criterion_definition_digest(criterion: dict) -> str:
    """Bind evidence to the meaning and identity of either criterion kind."""
    definition = {
        "version": 2,
        "id": criterion["id"],
        "kind": criterion["kind"],
        "description": criterion.get("description"),
    }
    if criterion["kind"] == "command":
        definition.update({
            "command": criterion["command"],
            "timeoutSeconds": criterion.get("timeoutSeconds", 600),
            "cwd": criterion.get("cwd"),
            "expect": criterion.get("expect"),
        })
    canonical = json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def command_definition_digest(criterion: dict) -> str:
    """Retain the command helper used by existing callers and tests."""
    return criterion_definition_digest(criterion)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_ignored_paths(paths: object) -> frozenset[str]:
    """Return safe repository-relative paths deliberately omitted from a fingerprint."""
    if paths is None:
        return frozenset()
    if not isinstance(paths, (set, frozenset, tuple, list)):
        raise ValueError("ignored paths must be a collection of safe relative paths")
    result: set[str] = set()
    for value in paths:
        if not isinstance(value, str) or not value or "\\" in value:
            raise ValueError("ignored path must be a nonempty portable relative path")
        relative = PurePosixPath(value)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("ignored path must stay within the repository")
        result.add(relative.as_posix())
    return frozenset(result)


def excluded(relative: PurePosixPath, ignored: frozenset[str] = frozenset()) -> bool:
    parts = tuple(part.lower() for part in relative.parts)
    name = parts[-1] if parts else ""
    return (
        relative.as_posix() in ignored
        or
        any(part in {".git", ".worktrees", "graphify-out", "__pycache__"} | SENSITIVE_DIRECTORIES for part in parts)
        or (len(parts) >= 2 and parts[:2] == (".harness", "acceptance"))
        or (len(parts) >= 2 and parts[:2] == (".harness", "work") and not name.endswith(".passport.json"))
        or (len(parts) >= 2 and parts[:2] == (".harness", "metrics"))
        or (len(parts) >= 3 and parts[:3] == (".harness", "benchmarks", "runs"))
        or name.endswith(".pyc")
        or any(fnmatch(name, pattern) for pattern in SENSITIVE_FILE_PATTERNS)
    )


def digest_files(base: Path, names: list[str], ignored: frozenset[str] = frozenset()) -> str:
    digest = hashlib.sha256()
    base_resolved = base.resolve()
    for name in sorted(names):
        relative = PurePosixPath(name)
        if excluded(relative, ignored):
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


def git_output(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=(root() if cwd is None else cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    ).stdout


def non_git_fingerprint(
    ignored: frozenset[str] = frozenset(), repository_root: Path | None = None
) -> dict[str, str]:
    base = (repository_root or root()).resolve()
    try:
        files = [path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file()]
        return {"algorithm": "sha256", "value": digest_files(base, files, ignored), "status": "ok"}
    except OSError:
        return {"algorithm": "sha256", "value": "", "status": "unavailable"}


def fingerprint(*, ignored_paths: object = None, repository_root: Path | None = None) -> dict[str, str]:
    """Return a deterministic safe project-state fingerprint, or explicit unavailability."""
    try:
        ignored = normalize_ignored_paths(ignored_paths)
        base = (repository_root or root()).resolve()

        def git(*args: str) -> str:
            if repository_root is None:
                return git_output(*args)
            return git_output(*args, cwd=base)

        git("rev-parse", "--is-inside-work-tree")
        index_digest = hashlib.sha256()
        for row in git("ls-files", "-s", "-z").split("\0"):
            if not row or "\t" not in row:
                continue
            metadata, name = row.split("\t", 1)
            if excluded(PurePosixPath(name), ignored):
                continue
            index_digest.update(metadata.encode("utf-8"))
            index_digest.update(b"\t")
            index_digest.update(name.encode("utf-8"))
            index_digest.update(b"\0")
        changed = [name for name in git("diff", "--name-only", "-z").split("\0") if name and not excluded(PurePosixPath(name), ignored)]
        untracked = [name for name in git("ls-files", "--others", "--exclude-standard", "-z").split("\0") if name and not excluded(PurePosixPath(name), ignored)]
        payload = json.dumps({
            "index": index_digest.hexdigest(),
            "worktree": digest_files(base, changed, ignored),
            "untracked": digest_files(base, untracked, ignored),
        }, sort_keys=True)
        return {"algorithm": "sha256", "value": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "status": "ok"}
    except (OSError, subprocess.SubprocessError):
        if (base / ".git").exists():
            return {"algorithm": "sha256", "value": "", "status": "unavailable"}
        return non_git_fingerprint(ignored, repository_root=base)


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
            evidence = args.evidence.strip()
            if not evidence:
                print("FAIL evidence must not be empty", file=sys.stderr)
                return 2
            current = fingerprint()
            if current.get("status") != "ok":
                print("FAIL repository fingerprint unavailable; manual evidence not recorded", file=sys.stderr)
                return 2
            criterion["passes"] = True
            criterion["evidence"] = evidence
            criterion["checkedAt"] = now_utc()
            criterion["durationMs"] = 0
            criterion["fingerprint"] = current
            criterion["definitionDigest"] = criterion_definition_digest(criterion)
            save(target, data)
            print(f"PASS recorded evidence for {args.criterion}")
            return 0
    print("FAIL criterion does not exist", file=sys.stderr)
    return 2


def stored_evidence_is_fresh(work_item: str, criterion_id: str) -> tuple[bool, str]:
    """Read stored criterion evidence without executing command criteria."""
    data = load(gate_path(work_item))
    for criterion in validate(data):
        if criterion["id"] != criterion_id:
            continue
        return evidence_freshness(criterion, fingerprint())
    return False, "missing stored acceptance criterion"


def evidence_freshness(criterion: dict, current: dict) -> tuple[bool, str]:
    evidence = str(criterion.get("evidence", "")).strip()
    stored = criterion.get("fingerprint")
    if not evidence or criterion.get("passes") is not True:
        return False, "missing stored acceptance evidence"
    if criterion.get("kind") == "command":
        try:
            resolve_cwd(criterion.get("cwd"))
        except (OSError, ValueError):
            return False, "stale command working directory"
    if criterion.get("definitionDigest") != criterion_definition_digest(criterion):
        if criterion.get("kind") == "command":
            return False, "stale command definition: reverify required"
        return False, "stale manual definition: re-prove required"
    if not isinstance(stored, dict) or stored.get("status") != "ok" or current.get("status") != "ok" or stored != current:
        return False, "stale stored acceptance evidence"
    return True, "fresh stored acceptance evidence"


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
        if criterion.get("definitionDigest") != criterion_definition_digest(criterion):
            return False, "stale manual definition: re-prove required"
        return criterion.get("passes") is True, "manual evidence"
    started = time.monotonic()
    criterion["checkedAt"] = now_utc()
    criterion["fingerprint"] = fingerprint()
    criterion["definitionDigest"] = command_definition_digest(criterion)
    if criterion["fingerprint"].get("status") != "ok":
        criterion["passes"] = False
        criterion["evidence"] = "auto: repository fingerprint unavailable; check not run"
        criterion["durationMs"] = max(0, round((time.monotonic() - started) * 1000))
        return False, criterion["evidence"]
    try:
        working_directory = resolve_cwd(criterion.get("cwd"))
        result = subprocess.run(
            criterion["command"], shell=True, cwd=working_directory, capture_output=True,
            text=True, timeout=criterion.get("timeoutSeconds", 600), encoding="utf-8", errors="replace",
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        expect = criterion.get("expect")
        marker_matches = expect is None or expect in output.splitlines()
        criterion["passes"] = result.returncode == 0 and marker_matches
        if expect is not None:
            result_note = "expected marker matched" if marker_matches else "expected marker missing"
        else:
            lines = output.strip().splitlines()
            result_note = lines[-1][:160] if lines else "no output"
        criterion["evidence"] = f"auto: exit {result.returncode}; {result_note}"
    except subprocess.TimeoutExpired:
        criterion["passes"] = False
        criterion["evidence"] = f"auto: timeout after {criterion.get('timeoutSeconds', 600)} seconds"
    except (OSError, ValueError):
        criterion["passes"] = False
        criterion["evidence"] = "auto: cwd unavailable or outside the repository; check not run"
    criterion["durationMs"] = max(0, round((time.monotonic() - started) * 1000))
    return criterion["passes"], criterion["evidence"]


def status(args: argparse.Namespace) -> int:
    """Report evidence freshness without executing criteria or writing the ledger."""
    target = gate_path(args.work_item)
    if not target.exists():
        print("FAIL gate does not exist", file=sys.stderr)
        return 2
    try:
        data = load(target)
        criteria = validate(data)
        current = fingerprint()
        results = [(criterion["id"], *evidence_freshness(criterion, current)) for criterion in criteria]
    except (ValueError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"FAIL invalid or uncheckable gate: {exc}", file=sys.stderr)
        return 2
    for cid, fresh, note in results:
        print(f"{'PASS' if fresh else 'FAIL'} {cid}: {note}")
    return 0 if all(fresh for _, fresh, _ in results) else 2


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
    p_status = sub.add_parser("status", help="read evidence freshness without running checks or writing the ledger")
    p_status.add_argument("work_item")
    p_status.set_defaults(func=status)
    p_reverify = sub.add_parser("reverify", help="rerun every command criterion and refresh its evidence")
    p_reverify.add_argument("work_item")
    p_reverify.set_defaults(func=check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
