"""Offline, owner-invoked distribution of an exact Harness release.

No downloads, scheduling, global configuration, project commands or AGENTS edits.
Only allowlisted core files are managed. A caller must establish an idle project
and review its instructions before apply. The lock serializes cooperating writers;
it does not lock editors or running agents. Interrupted transactions fail closed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

FILES = (
    "acceptance_gate.py", "goal_runner_validator.py", "goal_orchestrator.py",
    "goal_progress.py", "harness_metrics.py", "harness_benchmark.py",
    "update_impact.py", "update_radar.py", "scripts/Invoke-HarnessGate.ps1",
    "docs/ENGINEERING_LOOP.md", "templates/work-item.md",
    "templates/acceptance.example.json", "templates/goal-passport.example.json",
    "templates/project-profile.example.json", "templates/update-radar-task.md",
    "templates/update-candidate.example.json", "templates/update-batch.example.json",
    "tests/fixtures/hre-001-benchmark.json",
)
RELEASE = "harness-release.json"
RECEIPT = ".harness/distribution.json"
LOCK = ".harness/.distribution-lock"
LIMIT = 2_000_000
HEX = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class DistributionError(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


def checked_root(value):
    path = Path(value)
    if str(path).startswith(("\\\\", "//")):
        raise DistributionError("network/device roots are not local projects")
    if not path.is_absolute() or ".." in path.parts:
        raise DistributionError("project/source root must be an absolute existing directory")
    path = Path(os.path.abspath(path))
    if path == Path(path.anchor) or path == Path.home():
        raise DistributionError("drive/home root is not a project")
    if os.name == "nt":
        import ctypes
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) != 3:
            raise DistributionError("project/source must be on a local fixed drive")
    for part in reversed([path, *path.parents]):
        if part.exists() and is_link(part):
            raise DistributionError(f"reparse/symlink root is not supported: {part}")
    if not path.is_dir():
        raise DistributionError(f"root not available: {path}")
    return path


def safe_path(root, name):
    # Names come only from constants/validated exact manifests, never arbitrary paths.
    target = root / name
    for part in [target, *target.parents]:
        if part == root:
            break
        if part.is_symlink() or part.exists():
            if is_link(part):
                raise DistributionError(f"reparse/symlink path refused: {part}")
            if part != target and not part.is_dir():
                raise DistributionError(f"parent is not a directory: {part}")
    return target


def read_bytes(path):
    if not path.is_file() or path.stat().st_size > LIMIT:
        raise DistributionError(f"expected regular file <= {LIMIT} bytes: {path}")
    with path.open("rb") as stream:
        result = stream.read(LIMIT + 1)
    if len(result) > LIMIT:
        raise DistributionError(f"file grew beyond limit: {path}")
    return result


def optional_bytes(root, name):
    path = safe_path(root, name)
    return read_bytes(path) if path.exists() else None


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DistributionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse(data):
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=reject_duplicates)


def load_registry(path):
    value = parse(read_bytes(path))
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "projects"}:
        raise DistributionError("invalid registry fields")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise DistributionError("unsupported registry schema")
    entries = value["projects"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise DistributionError("registry requires 1-100 explicit projects")
    seen = set()
    active = []
    for entry in entries:
        required = {"name", "path", "hostId"}
        if not isinstance(entry, dict) or not required <= set(entry) or set(entry) - required - {"deferredReason"}:
            raise DistributionError("invalid project registry fields")
        if any(not isinstance(entry[k], str) or not entry[k].strip() for k in entry):
            raise DistributionError("registry values must be nonempty strings")
        root = Path(entry["path"])
        if entry["hostId"] != "local" or not root.is_absolute() or ".." in root.parts or str(root).startswith(("\\\\", "//")):
            raise DistributionError("registry requires absolute local project paths")
        key = os.path.normcase(os.path.abspath(root))
        if key in seen:
            raise DistributionError("duplicate project root")
        seen.add(key)
        if "deferredReason" not in entry:
            if any(root in other.parents or other in root.parents for other in active):
                raise DistributionError("overlapping active roots; explicitly defer a nested project")
            active.append(root)
    return value


def validate_manifest(value):
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "releaseId", "files", "bundleHash"}:
        raise DistributionError("invalid manifest fields")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise DistributionError("unsupported manifest schema")
    if not isinstance(value["releaseId"], str) or not VERSION.fullmatch(value["releaseId"]):
        raise DistributionError("invalid release ID")
    hashes = value["files"]
    if not isinstance(hashes, dict) or set(hashes) != set(FILES):
        raise DistributionError("manifest must contain exactly the fixed managed file list")
    if any(not isinstance(v, str) or not HEX.fullmatch(v) for v in hashes.values()):
        raise DistributionError("invalid file hash")
    expected = digest(encoded({"releaseId": value["releaseId"], "files": hashes}))
    if value["bundleHash"] != expected:
        raise DistributionError("invalid bundle hash")
    return value


def release_manifest(source, version):
    source = checked_root(source)
    files = {name: digest(read_bytes(safe_path(source, name))) for name in FILES}
    result = {"schemaVersion": 1, "releaseId": version, "files": files,
              "bundleHash": digest(encoded({"releaseId": version, "files": files}))}
    return validate_manifest(result)


def load_release(source):
    source = checked_root(source)
    manifest = validate_manifest(parse(read_bytes(safe_path(source, RELEASE))))
    payload = {name: read_bytes(safe_path(source, name)) for name in FILES}
    for name, content in payload.items():
        if digest(content) != manifest["files"][name]:
            raise DistributionError(f"release content mismatch: {name}")
        if name.endswith(".py"):
            ast.parse(content, filename=name)
        elif name.endswith(".json"):
            parse(content)
    return manifest, payload


def snapshot(project):
    return {name: optional_bytes(project, name) for name in (*FILES, RECEIPT)}


def inspect(source, project):
    source, project = checked_root(source), checked_root(project)
    if source == project or source in project.parents or project in source.parents:
        raise DistributionError("source and project roots must be separate and non-nested")
    if safe_path(project, LOCK).exists():
        raise DistributionError("installation lock exists; inspect interrupted/active transaction")
    manifest, payload = load_release(source)
    before = snapshot(project)
    prior = validate_manifest(parse(before[RECEIPT])) if before[RECEIPT] is not None else None
    rows = []
    for name in FILES:
        actual = digest(before[name]) if before[name] is not None else None
        wanted = manifest["files"][name]
        if prior is not None and actual != prior["files"][name]:
            action = "conflict"
        elif actual == wanted:
            action = "unchanged"
        elif actual is None:
            action = "create"
        elif prior is not None:
            action = "update"
        else:
            action = "conflict"
        rows.append({"path": name, "action": action, "beforeHash": actual, "afterHash": wanted})
    receipt_bytes = encoded(manifest)
    result = {"schemaVersion": 1, "project": str(project), "releaseId": manifest["releaseId"],
              "bundleHash": manifest["bundleHash"], "files": rows,
              "receiptChanged": before[RECEIPT] != receipt_bytes,
              "profileConfigured": (project / "harness.config.json").is_file(),
              "canApply": not any(row["action"] == "conflict" for row in rows)}
    result["planHash"] = digest(encoded({"plan": result, "receiptHash": digest(before[RECEIPT]) if before[RECEIPT] else None}))
    return result, manifest, payload, before


def atomic_write(path, content):
    fd, temporary = tempfile.mkstemp(prefix=".harness-distribution-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify(project, expected=None):
    project = checked_root(project)
    installed = validate_manifest(parse(read_bytes(safe_path(project, RECEIPT))))
    mismatches = [name for name in FILES if digest(read_bytes(safe_path(project, name))) != installed["files"][name]]
    if expected is not None and installed != expected:
        mismatches.append(RECEIPT)
    if mismatches:
        raise DistributionError("installed content mismatch: " + ", ".join(mismatches))
    return {"status": "verified", "project": str(project), "releaseId": installed["releaseId"],
            "bundleHash": installed["bundleHash"], "verifiedFiles": len(FILES),
            "profileConfigured": (project / "harness.config.json").is_file(),
            "projectAcceptance": "not-run"}


def apply(source, project, plan_hash, *, idle_confirmed=False):
    if idle_confirmed is not True:
        raise DistributionError("caller must confirm project idle and instructions reviewed")
    plan, manifest, payload, before = inspect(source, project)
    if not plan["canApply"] or plan_hash != plan["planHash"]:
        raise DistributionError("conflict or stale reviewed plan; no files changed")
    project = checked_root(project)
    changes = {name: payload[name] for name in FILES if before[name] != payload[name]}
    if before[RECEIPT] != encoded(manifest):
        changes[RECEIPT] = encoded(manifest)
    if not changes:
        return {**verify(project, manifest), "changed": False}
    control = safe_path(project, ".harness")
    control.mkdir(exist_ok=True)
    lock = safe_path(project, LOCK)
    lock.mkdir()  # Exclusive cooperating-writer lock; never auto-clear a stale lock.
    touched, created_dirs = [], []
    backup = None
    try:
        if snapshot(project) != before:
            raise DistributionError("project changed after reviewed plan")
        backup = safe_path(project, ".harness/distribution-backups") / uuid.uuid4().hex
        backup.mkdir(parents=True)
        for name in changes:
            if before[name] is not None:
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(before[name])
        # Retained on disk for crash recovery. It contains no project secrets/commands.
        (backup / "transaction.json").write_bytes(encoded({"state": "prepared", "files": [
            {"path": n, "beforeHash": digest(before[n]) if before[n] is not None else None,
             "afterHash": digest(changes[n])} for n in changes]}))
        for name, content in changes.items():
            path = safe_path(project, name)
            if optional_bytes(project, name) != before[name]:
                raise DistributionError(f"concurrent edit: {name}")
            missing = []
            parent = path.parent
            while not parent.exists():
                missing.append(parent)
                parent = parent.parent
            for directory in reversed(missing):
                directory.mkdir()
                created_dirs.append(directory)
            atomic_write(path, content)
            touched.append(name)
        result = verify(project, manifest)
        (backup / "state.txt").write_text("committed\n", encoding="ascii")
    except BaseException:
        rollback_failed = []
        for name in reversed(touched):
            try:
                path = safe_path(project, name)
                if optional_bytes(project, name) != changes[name]:
                    raise DistributionError("concurrent edit during rollback")
                if before[name] is None:
                    path.unlink()
                else:
                    atomic_write(path, before[name])
            except (OSError, ValueError):
                rollback_failed.append(name)
        if not rollback_failed:
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass  # Never remove foreign content.
            lock.rmdir()
        else:
            raise DistributionError("rollback incomplete; lock and backups retained: " + ", ".join(rollback_failed))
        raise
    lock.rmdir()
    return {**result, "changed": True, "backup": str(backup)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    release = sub.add_parser("release", help="print a manifest; does not publish or write it")
    release.add_argument("--source", required=True, type=Path)
    release.add_argument("--version", required=True)
    registry = sub.add_parser("registry", help="strictly validate and print a local project registry")
    registry.add_argument("--path", required=True, type=Path)
    for command in ("plan", "apply"):
        item = sub.add_parser(command)
        item.add_argument("--source", required=True, type=Path)
        item.add_argument("--project", required=True, type=Path)
        if command == "apply":
            item.add_argument("--plan-hash", required=True)
            item.add_argument("--idle-confirmed", action="store_true")
    item = sub.add_parser("verify")
    item.add_argument("--project", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "release":
            result = release_manifest(args.source, args.version)
        elif args.command == "registry":
            result = load_registry(args.path)
        elif args.command == "plan":
            result = inspect(args.source, args.project)[0]
        elif args.command == "apply":
            result = apply(args.source, args.project, args.plan_hash, idle_confirmed=args.idle_confirmed)
        else:
            result = verify(args.project)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2 if result.get("canApply") is False else 0
    except (OSError, ValueError, SyntaxError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
