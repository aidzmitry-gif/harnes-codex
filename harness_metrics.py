#!/usr/bin/env python3
"""Append-only, versioned JSONL telemetry for local harness runs."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from collections.abc import Iterable, Iterator
from typing import Any


SCHEMA_VERSION = 1
# ponytail: measured at 50,000 pair keys (1.763 s / 54.06 MiB); above this archive JSONL or add a SQLite index.
MAX_COMPARE_PAIR_KEYS = 50_000
EVENT_FIELDS = (
    "runId", "pairKey", "chainId", "subgoalId", "treatment", "mode", "model",
    "reasoningEffort", "inputTokens", "outputTokens", "durationMs", "attempts",
    "reworkCount", "accepted", "released", "used", "escapedDefects", "checksPassed",
    "checksFailed",
)
RECORD_FIELDS = ("schemaVersion", "recordedAt", *EVENT_FIELDS)
REQUIRED_FIELDS = {
    "runId", "pairKey", "treatment", "mode", "durationMs", "attempts", "reworkCount",
    "accepted", "escapedDefects", "checksPassed", "checksFailed",
}
TEXT_FIELDS = {
    "runId", "pairKey", "chainId", "subgoalId", "treatment", "mode", "model", "reasoningEffort",
}
COUNT_FIELDS = {
    "inputTokens", "outputTokens", "durationMs", "attempts", "reworkCount", "escapedDefects",
    "checksPassed", "checksFailed",
}
BOOL_FIELDS = {"accepted", "released", "used"}
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,255}$")
SECRET_PATTERN = re.compile(r"(?i)(?:bearer(?:[:=]|\s)|(?:api[_-]?key|token|secret|password)\s*[:=])")


def _fail(message: str) -> None:
    raise ValueError(message)


def validate_event(event: Any) -> dict[str, Any]:
    """Return a complete normalized event or reject untrusted event input."""
    if not isinstance(event, dict):
        _fail("event must be a JSON object")
    extra = set(event) - set(EVENT_FIELDS)
    if extra:
        _fail("unknown event fields: " + ", ".join(sorted(extra)))
    missing = REQUIRED_FIELDS - set(event)
    if missing:
        _fail("missing required event fields: " + ", ".join(sorted(missing)))

    normalized = {field: event.get(field) for field in EVENT_FIELDS}
    for field in TEXT_FIELDS:
        value = normalized[field]
        if value is None and field not in REQUIRED_FIELDS:
            continue
        if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
            _fail(f"{field} must be a bounded identifier using only ASCII letters, digits, '.', '_', ':', '/', '+', or '-'")
        if SECRET_PATTERN.search(value):
            _fail(f"{field} contains a secret-like value")
    for field in COUNT_FIELDS:
        value = normalized[field]
        if field in ("inputTokens", "outputTokens") and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            _fail(f"{field} must be a nonnegative integer")
    if (normalized["inputTokens"] is None) != (normalized["outputTokens"] is None):
        _fail("inputTokens and outputTokens must both be nonnegative integers or both null")
    if normalized["attempts"] < 1:
        _fail("attempts must be at least 1")
    for field in BOOL_FIELDS:
        value = normalized[field]
        if field in ("released", "used") and value is None:
            continue
        if not isinstance(value, bool):
            _fail(f"{field} must be boolean" + (" or null" if field in ("released", "used") else ""))
    if normalized["used"] is True and normalized["released"] is not True:
        _fail("used=true requires released=true")
    return normalized


def normalize_event(event: Any, recorded_at: str | None = None) -> dict[str, Any]:
    normalized = validate_event(event)
    timestamp = recorded_at or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"schemaVersion": SCHEMA_VERSION, "recordedAt": timestamp, **normalized}


def validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != set(RECORD_FIELDS):
        _fail("record has an invalid schema")
    if record["schemaVersion"] != SCHEMA_VERSION:
        _fail("unsupported schemaVersion")
    timestamp = record["recordedAt"]
    if not isinstance(timestamp, str):
        _fail("recordedAt must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("recordedAt must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        _fail("recordedAt must be UTC")
    normalize_event({field: record[field] for field in EVENT_FIELDS}, recorded_at=timestamp)
    return record


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Append exactly one UTF-8 JSONL record and force it to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                _fail("could not append complete telemetry record")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def iter_records(path: Path) -> Iterator[dict[str, Any]]:
    """Yield validated JSONL records without materializing the telemetry file."""
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read telemetry file: {exc}") from exc
    with handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                _fail(f"line {number}: blank lines are not valid JSONL records")
            try:
                yield validate_record(json.loads(line))
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"line {number}: {exc}") from exc


def load_records(path: Path) -> list[dict[str, Any]]:
    """Compatibility helper for callers that explicitly need a materialized list."""
    return list(iter_records(path))


def summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    runs = accepted = attempts = checks_failed = checks_passed = defects = rework = duration = 0
    token_known = token_input = token_output = 0
    release_known = released = usage_known = used = 0
    for record in records:
        runs += 1
        accepted += int(record["accepted"])
        attempts += record["attempts"]
        checks_failed += record["checksFailed"]
        checks_passed += record["checksPassed"]
        defects += record["escapedDefects"]
        rework += record["reworkCount"]
        duration += record["durationMs"]
        if record["inputTokens"] is not None:
            token_known += 1
            token_input += record["inputTokens"]
            token_output += record["outputTokens"]
        if record["released"] is not None:
            release_known += 1
            released += int(record["released"])
        if record["used"] is not None:
            usage_known += 1
            used += int(record["used"])
    return {
        "accepted": accepted,
        "attemptsTotal": attempts,
        "checks": {"failed": checks_failed, "passed": checks_passed},
        "durationMsMean": duration / runs if runs else None,
        "escapedDefects": defects,
        "passRate": accepted / runs if runs else None,
        "release": {"known": release_known, "rate": released / release_known if release_known else None, "released": released},
        "reworkTotal": rework,
        "runs": runs,
        "tokens": {
            "input": token_input if token_known else None,
            "knownCoverage": token_known / runs if runs else None,
            "knownRuns": token_known,
            "output": token_output if token_known else None,
            "total": token_input + token_output if token_known else None,
        },
        "usage": {"known": usage_known, "rate": used / usage_known if usage_known else None, "used": used},
    }


def _mean_delta(pairs: list[tuple[dict[str, Any], dict[str, Any]]], field: str, optional: bool = False) -> dict[str, Any]:
    values: list[float] = []
    for baseline, treatment in pairs:
        if field == "knownTotalTokens":
            before = None if baseline["inputTokens"] is None else baseline["inputTokens"] + baseline["outputTokens"]
            after = None if treatment["inputTokens"] is None else treatment["inputTokens"] + treatment["outputTokens"]
        else:
            before, after = baseline[field], treatment[field]
        if optional and (before is None or after is None):
            continue
        values.append(float(after) - float(before))
    return {"mean": fmean(values) if values else None, "pairs": len(values)}


def compare(records: Iterable[dict[str, Any]], baseline_id: str, treatment_id: str) -> dict[str, Any]:
    if baseline_id == treatment_id:
        _fail("baseline and treatment must differ")
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for record in records:
        pair_key = record["pairKey"]
        if pair_key not in grouped and len(grouped) >= MAX_COMPARE_PAIR_KEYS:
            _fail(f"compare supports at most {MAX_COMPARE_PAIR_KEYS} pair keys in memory; archive the JSONL or add a SQLite index")
        bucket = grouped.setdefault(pair_key, {baseline_id: [], treatment_id: []})
        if record["treatment"] in bucket:
            bucket[record["treatment"]].append(record)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    exclusions = {"duplicateBaseline": 0, "duplicateTreatment": 0, "missingBaseline": 0, "missingTreatment": 0}
    for bucket in grouped.values():
        base, treat = bucket[baseline_id], bucket[treatment_id]
        if len(base) != 1 or len(treat) != 1:
            if not base:
                exclusions["missingBaseline"] += 1
            elif len(base) > 1:
                exclusions["duplicateBaseline"] += 1
            if not treat:
                exclusions["missingTreatment"] += 1
            elif len(treat) > 1:
                exclusions["duplicateTreatment"] += 1
            continue
        pairs.append((base[0], treat[0]))
    return {
        "baseline": baseline_id,
        "deltas": {
            "accepted": _mean_delta(pairs, "accepted"),
            "defects": _mean_delta(pairs, "escapedDefects"),
            "durationMs": _mean_delta(pairs, "durationMs"),
            "knownTotalTokens": _mean_delta(pairs, "knownTotalTokens", optional=True),
            "release": _mean_delta(pairs, "released", optional=True),
            "rework": _mean_delta(pairs, "reworkCount"),
            "usage": _mean_delta(pairs, "used", optional=True),
        },
        "exclusions": exclusions,
        "pairs": len(pairs),
        "treatment": treatment_id,
    }


def _dump(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--file", required=True, type=Path)
    record.add_argument("--from", dest="event_file", required=True, type=Path)
    summary_command = commands.add_parser("summary")
    summary_command.add_argument("--file", required=True, type=Path)
    compare_command = commands.add_parser("compare")
    compare_command.add_argument("--file", required=True, type=Path)
    compare_command.add_argument("--baseline", required=True)
    compare_command.add_argument("--treatment", required=True)
    args = parser.parse_args()
    try:
        if args.command == "record":
            event = json.loads(args.event_file.read_text(encoding="utf-8"))
            normalized = normalize_event(event)
            append_record(args.file, normalized)
            _dump(normalized)
        elif args.command == "summary":
            _dump(summary(iter_records(args.file)))
        else:
            _dump(compare(iter_records(args.file), args.baseline, args.treatment))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
