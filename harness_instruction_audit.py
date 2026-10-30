"""Report-only audit for an explicit, bounded list of changed Markdown instructions."""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import harness_distribution as distribution


# ponytail: cap at 128 change entries, 2 MB input, 1,000 findings, and 32 locations/group; raise after a measured larger bounded suite.
MAX_CHANGE_ENTRIES = 128
MAX_INSTRUCTION_BYTES = 2_000_000
MAX_FINDINGS = 1_000
MAX_DUPLICATE_LOCATIONS = 32
MANIFEST_LIMIT = distribution.LIMIT
BACKTICK = chr(96)
INLINE_LINK = re.compile(
    r"(?<!!)\[([^\]\n]+)\]\(\s*(?:<([^>\n]*)>|([^\s()<>]+))"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]+\)))?\s*\)"
)
FENCE = re.compile(r"^ {0,3}(" + re.escape(BACKTICK) + r"{3,}|~{3,})")
WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
WINDOWS_DEVICE = re.compile(r"^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?$", re.I)
WINDOWS_DEVICE_PREFIX = re.compile(r"^//[?.]/")
SECRET_STEM = re.compile(
    r"^(?:secret|secrets|credential|credentials|token|tokens|password|passwords|passwd|"
    r"auth|authorization|api[_-]?key|client[_-]?secret|oauth[_-]?tokens?|"
    r"access[_-]?tokens?|refresh[_-]?tokens?|private[_-]?key)(?:$|[._-])"
)


class AuditError(ValueError):
    """Safe, content-free refusal code for invalid or unsafe audit inputs."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _sensitive_component(component: str) -> bool:
    folded = component.casefold()
    if folded in {".ssh", ".aws", ".netrc", "_netrc", ".npmrc", ".pypirc", "private"}:
        return True
    if folded == ".env" or folded.startswith((".env.", ".env-")):
        return True
    if folded in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}:
        return True
    stem = Path(folded).stem
    if SECRET_STEM.match(stem) or stem in {"git-credentials"}:
        return True
    return Path(folded).suffix.casefold() in {".pem", ".key", ".p12", ".pfx", ".kdbx"}


def validate_repo_path(value: object, *, markdown: bool = False, allow_root: bool = False) -> str:
    """Validate a canonical repo-relative POSIX path before any filesystem helper sees it."""
    if not isinstance(value, str) or not value or len(value) > 4_096:
        raise AuditError("invalid_path")
    if "\x00" in value or "\\" in value or ":" in value or value.startswith("/"):
        raise AuditError("unsafe_path_refused")
    parts = value.split("/")
    if allow_root and value == ".":
        return value
    if any(part in {"", ".", ".."} for part in parts):
        raise AuditError("unsafe_path_refused")
    if any(part.endswith((" ", ".")) or WINDOWS_DEVICE.fullmatch(part) for part in parts):
        raise AuditError("unsafe_path_refused")
    if any(_sensitive_component(part) for part in parts):
        raise AuditError("secret_path_refused")
    if any(ord(char) < 32 for char in value):
        raise AuditError("unsafe_path_refused")
    if markdown and Path(parts[-1]).suffix.casefold() not in {".md", ".markdown"}:
        raise AuditError("markdown_path_required")
    return value


def validate_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "allowedPaths", "changes"}:
        raise AuditError("invalid_manifest_shape")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise AuditError("unsupported_manifest_version")
    allowed, changes = value["allowedPaths"], value["changes"]
    if not isinstance(allowed, list) or not isinstance(changes, list) or len(changes) > MAX_CHANGE_ENTRIES:
        raise AuditError("manifest_limit_or_type")
    allowed_paths = [validate_repo_path(item, markdown=True) for item in allowed]
    if len(set(allowed_paths)) != len(allowed_paths):
        raise AuditError("duplicate_allowlist_path")

    normalized, referenced = [], []
    for item in changes:
        if not isinstance(item, dict) or not isinstance(item.get("status"), str):
            raise AuditError("invalid_change_entry")
        status = item["status"]
        if status in {"added", "modified", "unchanged", "deleted"}:
            if set(item) != {"status", "path"}:
                raise AuditError("invalid_change_entry")
            path = validate_repo_path(item["path"], markdown=True)
            referenced.append(path)
            normalized.append({"status": status, "path": path})
        elif status == "renamed":
            if set(item) != {"status", "from", "to"}:
                raise AuditError("invalid_change_entry")
            old = validate_repo_path(item["from"], markdown=True)
            new = validate_repo_path(item["to"], markdown=True)
            if old == new:
                raise AuditError("invalid_change_entry")
            referenced.extend((old, new))
            normalized.append({"status": status, "from": old, "to": new})
        else:
            raise AuditError("invalid_change_status")
    if len(set(referenced)) != len(referenced):
        raise AuditError("duplicate_change_path")
    if set(referenced) != set(allowed_paths):
        raise AuditError("allowlist_mismatch")
    return {"schemaVersion": 1, "allowedPaths": allowed_paths, "changes": normalized}


def parse_manifest(data: bytes) -> dict:
    if len(data) > MANIFEST_LIMIT:
        raise AuditError("manifest_too_large")
    try:
        value = distribution.parse(data)
    except (UnicodeDecodeError, ValueError, distribution.DistributionError):
        raise AuditError("invalid_manifest_json") from None
    return validate_manifest(value)


def _checked_path(root: Path, relative: str) -> Path:
    # Pass only validated names: distribution.safe_path assumes exact/validated paths.
    try:
        return distribution.safe_path(root, relative)
    except (OSError, ValueError, distribution.DistributionError):
        raise AuditError("unsafe_path_refused") from None


def _path_exists(path: Path) -> bool:
    return path.exists()


def _path_is_file(path: Path) -> bool:
    return path.is_file()


def _path_size(path: Path) -> int:
    return path.stat().st_size


def _read_path(path: Path) -> bytes:
    return distribution.read_bytes(path)


def _fenced_or_code_line(line: str, fence):
    match = FENCE.match(line)
    if fence:
        if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= fence[1]:
            if not line[match.end():].strip():
                return True, None
        return True, fence
    if match:
        marker = match.group(1)
        return True, (marker[0], len(marker))
    return False, None


def _without_inline_code(line: str) -> str:
    output, index = [], 0
    while index < len(line):
        if line[index] != BACKTICK:
            output.append(line[index])
            index += 1
            continue
        end_run = index + 1
        while end_run < len(line) and line[end_run] == BACKTICK:
            end_run += 1
        marker = line[index:end_run]
        end_code = line.find(marker, end_run)
        if end_code < 0:
            output.append(marker)
            index = end_run
        else:
            index = end_code + len(marker)
    return "".join(output)


def inline_markdown_links(text: str):
    """Yield destinations for ordinary inline Markdown links, outside code spans/fences."""
    fence = None
    for line_number, line in enumerate(text.splitlines(), 1):
        skip, fence = _fenced_or_code_line(line, fence)
        if skip:
            continue
        for match in INLINE_LINK.finditer(_without_inline_code(line)):
            yield line_number, match.group(2) if match.group(2) is not None else match.group(3)


def _resolve_local_link(source: str, destination: str) -> tuple[str, str | None]:
    if not isinstance(destination, str) or len(destination) > 4_096:
        return "unsafe", None
    if WINDOWS_DEVICE_PREFIX.match(destination) or "\\" in destination or WINDOWS_DRIVE.match(destination):
        return "unsafe", None
    if destination.startswith("//"):
        return "external", None
    try:
        parsed = urlsplit(destination)
    except ValueError:
        return "unsafe", None
    if parsed.scheme:
        return ("unsafe", None) if parsed.scheme.casefold() == "file" else ("external", None)
    if parsed.netloc:
        return "external", None
    try:
        raw_path = unquote(parsed.path, errors="strict")
    except (UnicodeDecodeError, ValueError):
        return "unsafe", None
    if not raw_path:
        return "same-page", None
    if raw_path.startswith("/") or "\\" in raw_path or ":" in raw_path or "\x00" in raw_path:
        return "unsafe", None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), raw_path))
    if target == ".." or target.startswith("../") or target.startswith("/"):
        return "unsafe", None
    try:
        validate_repo_path(target, allow_root=True)
    except AuditError as error:
        return ("secret", None) if error.code == "secret_path_refused" else ("unsafe", None)
    return "local", target


def _location(path: str, line: int) -> dict:
    return {"path": path, "line": line}


def audit_manifest(root: Path, raw_manifest: object) -> dict:
    manifest = validate_manifest(raw_manifest)
    changes = manifest["changes"]
    paths = sorted(manifest["allowedPaths"])
    # Refuse every unsafe changed path before reading any changed instruction.
    guarded = {name: _checked_path(root, name) for name in paths}
    read_names = [
        change["path"] if change["status"] in {"added", "modified"} else change["to"]
        for change in changes
        if change["status"] in {"added", "modified", "renamed"}
    ]

    sizes, total = {}, 0
    for name in read_names:
        path = guarded[name]
        if not _path_exists(path):
            continue
        if not _path_is_file(path):
            raise AuditError("changed_path_not_regular_file")
        try:
            size = _path_size(path)
        except OSError:
            raise AuditError("changed_path_unavailable") from None
        if size > distribution.LIMIT:
            raise AuditError("instruction_file_too_large")
        total += size
        if total > MAX_INSTRUCTION_BYTES:
            raise AuditError("instruction_byte_limit")
        sizes[name] = size

    findings, truncated = [], False

    def add(item):
        nonlocal truncated
        if len(findings) < MAX_FINDINGS:
            findings.append(item)
        else:
            truncated = True

    texts, counts = {}, {s: 0 for s in ("added", "modified", "unchanged", "deleted", "renamed")}
    for change in changes:
        status = change["status"]
        counts[status] += 1
        if status == "unchanged":
            add({"kind": "unchanged-skipped", "path": change["path"]})
            continue
        if status == "deleted":
            add({"kind": "deleted-not-read", "path": change["path"]})
            if _path_exists(guarded[change["path"]]):
                add({"kind": "deleted-path-still-present", "path": change["path"]})
            continue
        if status == "renamed":
            old, name = change["from"], change["to"]
            add({"kind": "renamed-path", "from": old, "to": name, "oldContentRead": False})
            if _path_exists(guarded[old]):
                add({"kind": "rename-source-still-present", "path": old})
            if not _path_exists(guarded[name]):
                add({"kind": "renamed-target-missing", "path": name})
                continue
        else:
            name = change["path"]
            if not _path_exists(guarded[name]):
                add({"kind": "changed-file-missing", "path": name})
                continue

        path = _checked_path(root, name)
        if not _path_is_file(path):
            raise AuditError("changed_path_not_regular_file")
        try:
            data = _read_path(path)
        except (OSError, ValueError, distribution.DistributionError):
            raise AuditError("changed_file_read_refused") from None
        if len(data) > sizes.get(name, 0):
            raise AuditError("changed_file_grew_during_read")
        try:
            texts[name] = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AuditError("changed_file_encoding_refused") from None

    for source in sorted(texts):
        for line, destination in inline_markdown_links(texts[source]):
            kind, target = _resolve_local_link(source, destination)
            where = _location(source, line)
            if kind in {"external", "same-page"}:
                continue
            if kind in {"unsafe", "secret"}:
                add({"kind": "unsafe-link-refused", "source": where})
                continue
            if not _path_exists(_checked_path(root, target)):
                add({"kind": "broken-local-link", "source": where, "target": target})

    candidates = {}
    for source, text in sorted(texts.items()):
        for line_number, line in enumerate(text.splitlines(), 1):
            normalized = re.sub(r"\s+", " ", line).strip().casefold()
            if normalized:
                candidate = candidates.setdefault(normalized, {"count": 0, "locations": []})
                candidate["count"] += 1
                if len(candidate["locations"]) < MAX_DUPLICATE_LOCATIONS:
                    candidate["locations"].append(_location(source, line_number))
    candidate_count = 0
    for normalized in sorted(candidates):
        candidate = candidates[normalized]
        if candidate["count"] < 2:
            continue
        candidate_count += 1
        add({
            "kind": "duplicate-candidate",
            "candidate": candidate_count,
            "match": "identical normalized nonempty line; human review required",
            "occurrenceCount": candidate["count"],
            "locations": candidate["locations"],
            "locationsTruncated": candidate["count"] > len(candidate["locations"]),
        })

    file_coverage = []
    for change in changes:
        status = change["status"]
        if status == "renamed":
            file_coverage.append({
                "status": status,
                "from": change["from"],
                "to": change["to"],
                "oldContentRead": False,
                "newContentRead": change["to"] in texts,
            })
        elif status in {"unchanged", "deleted"}:
            file_coverage.append({"status": status, "path": change["path"], "contentRead": False})
        else:
            file_coverage.append({
                "status": status,
                "path": change["path"],
                "contentRead": change["path"] in texts,
            })

    findings.sort(key=lambda item: (
        str(item.get("path", item.get("source", {}).get("path", item.get("to", "")))),
        int(item.get("source", {}).get("line", 0)),
        item["kind"],
    ))
    return {
        "schemaVersion": 1,
        "status": "report-only",
        "findings": findings,
        "coverage": {
            "manifestChangeEntries": len(changes),
            "statusCounts": counts,
            "auditedChangedFiles": len(texts),
            "fileCoverage": file_coverage,
            "externalLinksFetched": 0,
            "linkTargetContentRead": 0,
            "duplicateCandidateGroups": candidate_count,
            "findingsTruncated": truncated,
            "parser": "ordinary inline Markdown links outside fenced and inline code spans only",
            "notParsed": [
                "reference-style links", "autolinks", "HTML links",
                "nested labels, unbracketed destinations with parentheses, escaped code delimiters",
            ],
            "semanticConflicts": "not assessed; human/source review required",
            "secretPathScreening": "common filename patterns only; content under other names is not scanned",
            "limits": {
                "manifestBytes": MANIFEST_LIMIT,
                "changeEntries": MAX_CHANGE_ENTRIES,
                "changedInstructionBytesTotal": MAX_INSTRUCTION_BYTES,
                "findings": MAX_FINDINGS,
                "duplicateLocationsPerCandidate": MAX_DUPLICATE_LOCATIONS,
            },
        },
    }


def run(root_value: str, manifest_value: str) -> dict:
    name = validate_repo_path(manifest_value)
    if Path(name).suffix.casefold() != ".json":
        raise AuditError("manifest_path_required")
    try:
        root = distribution.checked_root(root_value)
    except (OSError, ValueError, distribution.DistributionError):
        raise AuditError("root_refused") from None
    path = _checked_path(root, name)
    if not _path_is_file(path):
        raise AuditError("manifest_not_regular_file")
    try:
        size = _path_size(path)
    except OSError:
        raise AuditError("manifest_read_refused") from None
    if size > MANIFEST_LIMIT:
        raise AuditError("manifest_too_large")
    try:
        data = _read_path(path)
    except (OSError, ValueError, distribution.DistributionError):
        raise AuditError("manifest_read_refused") from None
    return audit_manifest(root, parse_manifest(data))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit",), help="produce a report; no diff or instruction commands run")
    parser.add_argument("--root", required=True, help="absolute local repository root")
    parser.add_argument("--manifest", required=True, help="repo-relative JSON change manifest")
    args = parser.parse_args(argv)
    try:
        result = run(args.root, args.manifest)
    except AuditError as error:
        print(json.dumps({"schemaVersion": 1, "status": "refused", "reason": error.code}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
