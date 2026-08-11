#!/usr/bin/env python3
"""Deduplicate and summarize structured OpenAI update candidates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import update_impact


SCHEMA_VERSION = 1
MAX_BATCH = 64
MAX_SEEN = 4096
MAX_INPUT_BYTES = 1_000_000
BATCH_FIELDS = {"schemaVersion", "candidates"}
STATE_FIELDS = {"schemaVersion", "seen"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RadarError(ValueError):
    """The batch or durable state is unsafe or outside the supported schema."""


def _exact_schema_version(value: object, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value != SCHEMA_VERSION:
        raise RadarError(f"{context}.schemaVersion must be integer 1")


def _validate_batch(batch: object) -> list[dict[str, object]]:
    if not isinstance(batch, dict) or set(batch) != BATCH_FIELDS:
        raise RadarError("batch must contain exactly schemaVersion and candidates")
    _exact_schema_version(batch["schemaVersion"], "batch")
    candidates = batch["candidates"]
    if not isinstance(candidates, list) or len(candidates) > MAX_BATCH:
        raise RadarError(f"batch.candidates must contain 0..{MAX_BATCH} entries")

    validated = []
    identifiers = set()
    for index, candidate in enumerate(candidates):
        try:
            result = update_impact.classify(candidate)
        except update_impact.CandidateError as exc:
            raise RadarError(f"batch.candidates[{index}] is invalid: {exc}") from exc
        identifier = result["id"]
        if identifier in identifiers:
            raise RadarError(f"batch contains duplicate candidate id: {identifier}")
        identifiers.add(identifier)
        assert isinstance(candidate, dict)
        validated.append({"candidate": candidate, "classification": result})
    return validated


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise RadarError(f"state exceeds {MAX_INPUT_BYTES} bytes")
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RadarError(f"state is unreadable: {exc}") from exc
    if not isinstance(state, dict) or set(state) != STATE_FIELDS:
        raise RadarError("state must contain exactly schemaVersion and seen")
    _exact_schema_version(state["schemaVersion"], "state")
    seen = state["seen"]
    if not isinstance(seen, dict) or len(seen) > MAX_SEEN:
        raise RadarError(f"state.seen must contain at most {MAX_SEEN} entries")
    for identifier, digest in seen.items():
        if not isinstance(identifier, str) or not update_impact.IDENTIFIER.fullmatch(identifier):
            raise RadarError("state.seen contains an invalid candidate id")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise RadarError(f"state.seen[{identifier}] must be a lowercase SHA-256 digest")
    return dict(seen)


def _digest(candidate: dict[str, object]) -> str:
    canonical = json.dumps(candidate, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_state(path: Path, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"schemaVersion": SCHEMA_VERSION, "seen": seen},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def scan(batch: object, state_path: Path) -> dict[str, object]:
    """Classify unseen candidates and atomically advance durable state."""
    validated = _validate_batch(batch)
    seen = _load_state(state_path)
    additions: dict[str, str] = {}
    new_results = []
    repeated = 0

    for item in sorted(validated, key=lambda entry: entry["classification"]["id"]):
        candidate = item["candidate"]
        classification = item["classification"]
        identifier = classification["id"]
        digest = _digest(candidate)
        previous = seen.get(identifier)
        if previous is not None:
            if previous != digest:
                raise RadarError(f"candidate id {identifier} conflicts with previously recorded content; use a new id")
            repeated += 1
            continue
        additions[identifier] = digest
        new_results.append(classification)

    if len(seen) + len(additions) > MAX_SEEN:
        raise RadarError(f"recording this batch would exceed the {MAX_SEEN}-candidate state limit")

    significant = sum(result["classification"] == "significant" for result in new_results)
    evaluate = sum(result["classification"] == "evaluate" for result in new_results)
    ignored = sum(result["classification"] == "ignore" for result in new_results)
    if significant:
        status = "meaningful-updates"
        message = "Есть обновления с потенциально значимым влиянием на Harness; требуется локальная проверка до внедрения."
    elif evaluate:
        status = "updates-need-evidence"
        message = "Обнаружены новые обновления, но влияние на Harness ещё требует доказательств."
    else:
        status = "no-meaningful-updates"
        message = "Значимых обновлений для Harness нет."

    if additions:
        next_seen = dict(sorted({**seen, **additions}.items()))
        _write_state(state_path, next_seen)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "message": message,
        "counts": {
            "input": len(validated),
            "new": len(new_results),
            "repeated": repeated,
            "significant": significant,
            "evaluate": evaluate,
            "ignored": ignored,
        },
        "candidates": new_results,
        "stateChanged": bool(additions),
        "stateCount": len(seen) + len(additions),
    }


def _read_batch(path: Path) -> object:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise RadarError(f"batch exceeds {MAX_INPUT_BYTES} bytes")
    return json.loads(path.read_text(encoding="utf-8"))


def _runtime_state_path(value: str) -> Path:
    runtime_root = (Path.cwd() / ".harness" / "runtime").resolve()
    path = Path(value).resolve()
    try:
        path.relative_to(runtime_root)
    except ValueError as exc:
        raise RadarError("state path must stay inside .harness/runtime") from exc
    if path == runtime_root or path.suffix.lower() != ".json":
        raise RadarError("state path must name a JSON file inside .harness/runtime")
    return path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) == 2 and argv[0] == "scan":
        batch_name = argv[1]
        state_name = ".harness/runtime/update-radar-state.json"
    elif len(argv) == 4 and argv[0] == "scan" and argv[2] == "--state":
        batch_name = argv[1]
        state_name = argv[3]
    else:
        print("usage: update_radar.py scan BATCH.json [--state .harness/runtime/STATE.json]", file=sys.stderr)
        return 2
    try:
        batch = _read_batch(Path(batch_name))
        result = scan(batch, _runtime_state_path(state_name))
    except (OSError, UnicodeError, json.JSONDecodeError, RadarError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
