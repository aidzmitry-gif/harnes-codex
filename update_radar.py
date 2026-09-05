#!/usr/bin/env python3
"""Single-writer tracker: discovery is separate from local evaluation attestations.

Callers must serialize scan/resolve for each state file. Atomic replacement
protects a failed write, not concurrent read-modify-write transactions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import update_impact


SCHEMA_VERSION = 1
STATE_VERSION = 2
MAX_BATCH = 64
MAX_SEEN = 4096
MAX_INPUT_BYTES = 1_000_000
BATCH_FIELDS = {"schemaVersion", "candidates"}
STATE_FIELDS = {"schemaVersion", "seen", "evaluations"}
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


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"schemaVersion": STATE_VERSION, "seen": {}, "evaluations": {}}
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise RadarError(f"state exceeds {MAX_INPUT_BYTES} bytes")
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RadarError(f"state is unreadable: {exc}") from exc
    if not isinstance(state, dict):
        raise RadarError("state must be an object")
    version = state.get("schemaVersion")
    if type(version) is not int or version not in (1, STATE_VERSION):
        raise RadarError("state.schemaVersion must be integer 1 or 2")
    fields = {"schemaVersion", "seen"} if version == 1 else STATE_FIELDS
    if set(state) != fields:
        raise RadarError("state has invalid fields for its schemaVersion")
    seen = state["seen"]
    if not isinstance(seen, dict) or len(seen) > MAX_SEEN:
        raise RadarError(f"state.seen must contain at most {MAX_SEEN} entries")
    for identifier, digest in seen.items():
        if not isinstance(identifier, str) or not update_impact.IDENTIFIER.fullmatch(identifier):
            raise RadarError("state.seen contains an invalid candidate id")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise RadarError(f"state.seen[{identifier}] must be a lowercase SHA-256 digest")
    evaluations = state.get("evaluations", {})
    if not isinstance(evaluations, dict) or not evaluations.keys() <= seen.keys():
        raise RadarError("state.evaluations must reference only seen candidate IDs")
    for identifier, evaluation in evaluations.items():
        if not isinstance(evaluation, dict) or set(evaluation) != {"classification", "resolution"}:
            raise RadarError(f"state.evaluations[{identifier}] has invalid fields")
        classification = evaluation["classification"]
        if not isinstance(classification, str) or classification not in {"significant", "evaluate", "ignore"}:
            raise RadarError("evaluation classification is invalid")
        resolution = evaluation["resolution"]
        if resolution is not None:
            if classification == "ignore":
                raise RadarError("ignored candidates cannot have a resolution")
            _validate_resolution(resolution)
    # Missing metadata is legacy-unknown, never an inferred successful evaluation.
    # Conversion stays in memory until a valid observation or resolution changes state.
    return {"schemaVersion": STATE_VERSION, "seen": seen, "evaluations": evaluations}


def _validate_resolution(resolution: object) -> None:
    if not isinstance(resolution, dict) or set(resolution) != {"outcome", "evidenceHash"}:
        raise RadarError("resolution must contain only outcome and evidenceHash")
    outcome = resolution["outcome"]
    if not isinstance(outcome, str) or outcome not in {"useful", "no-benefit"}:
        raise RadarError("resolution outcome must be useful or no-benefit")
    if not isinstance(resolution["evidenceHash"], str) or not SHA256.fullmatch(resolution["evidenceHash"]):
        raise RadarError("resolution evidenceHash must be a lowercase SHA-256 digest")


def _digest(candidate: dict[str, object]) -> str:
    canonical = json.dumps(candidate, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_state(path: Path, state: dict) -> None:
    payload = json.dumps(
        state,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    if len(payload.encode("utf-8")) > MAX_INPUT_BYTES:
        raise RadarError(f"next state would exceed {MAX_INPUT_BYTES} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def scan(batch: object, state_path: Path) -> dict[str, object]:
    """Observe candidates; pending work survives exact repeats and empty batches."""
    validated = _validate_batch(batch)
    state = _load_state(state_path)
    seen, evaluations = state["seen"], state["evaluations"]
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
            if identifier in evaluations:
                continue
        else:
            additions[identifier] = digest
        new_results.append(classification)

    if len(seen) + len(additions) > MAX_SEEN:
        raise RadarError(f"recording this batch would exceed the {MAX_SEEN}-candidate state limit")

    for result in new_results:
        evaluations[result["id"]] = {"classification": result["classification"], "resolution": None}
    seen.update(additions)
    pending = [
        {"id": identifier, "digest": seen[identifier], "classification": item["classification"]}
        for identifier, item in sorted(evaluations.items())
        if item["classification"] != "ignore" and item["resolution"] is None
    ]
    unknown = len(seen) - len(evaluations)
    significant = sum(result["classification"] == "significant" for result in new_results)
    evaluate = sum(result["classification"] == "evaluate" for result in new_results)
    ignored = sum(result["classification"] == "ignore" for result in new_results)
    if significant:
        status = "meaningful-updates"
        message = "Есть обновления с потенциально значимым влиянием на Harness; требуется локальная проверка до внедрения."
    elif evaluate:
        status = "updates-need-evidence"
        message = "Обнаружены новые обновления, но влияние на Harness ещё требует доказательств."
    elif pending:
        status = "pending-evaluation"
        message = "Есть незавершённые локальные оценки; новых кандидатов для оценки нет."
    elif unknown:
        status = "evaluation-history-unknown"
        message = "История обнаружения есть, но результаты прежних оценок неизвестны."
    else:
        status = "no-meaningful-updates"
        message = "Значимых обновлений для Harness нет."

    if new_results:
        _write_state(state_path, state)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "message": message,
        "counts": {
            "input": len(validated),
            "new": len(additions),
            "repeated": repeated,
            "significant": significant,
            "evaluate": evaluate,
            "ignored": ignored,
        },
        "candidates": new_results,
        "pending": pending,
        "pendingCount": len(pending),
        "unknownEvaluationCount": unknown,
        "stateChanged": bool(new_results),
        "stateCount": len(seen),
    }


def resolve(identifier: str, digest: str, outcome: str, evidence_hash: str, state_path: Path) -> dict:
    """Record a caller's local-evaluation attestation, never adopt an update."""
    if not isinstance(identifier, str) or not update_impact.IDENTIFIER.fullmatch(identifier):
        raise RadarError("resolution id must be a bounded candidate identifier")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise RadarError("resolution digest must be a lowercase SHA-256 digest")
    resolution = {"outcome": outcome, "evidenceHash": evidence_hash}
    _validate_resolution(resolution)
    state = _load_state(state_path)
    if state["seen"].get(identifier) != digest:
        raise RadarError("resolution id/digest does not match observed history")
    evaluation = state["evaluations"].get(identifier)
    if evaluation is None or evaluation["classification"] == "ignore":
        raise RadarError("resolution requires an observed actionable candidate")
    previous = evaluation["resolution"]
    if previous is not None and previous != resolution:
        raise RadarError("resolution conflicts with recorded history; do not rewrite evidence")
    changed = previous is None
    if changed:
        evaluation["resolution"] = resolution
        _write_state(state_path, state)
    return {"schemaVersion": SCHEMA_VERSION, "status": "evaluation-recorded", "id": identifier,
            "digest": digest, "outcome": outcome, "evidenceHash": evidence_hash, "stateChanged": changed}


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
    parser = argparse.ArgumentParser(prog="update_radar.py")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("batch")
    resolve_parser = commands.add_parser("resolve")
    resolve_parser.add_argument("id")
    resolve_parser.add_argument("--digest", required=True)
    resolve_parser.add_argument("--outcome", choices=("useful", "no-benefit"), required=True)
    resolve_parser.add_argument("--evidence-hash", required=True)
    for subparser in (scan_parser, resolve_parser):
        subparser.add_argument("--state", default=".harness/runtime/update-radar-state.json")
    args = parser.parse_args(argv)
    try:
        state_path = _runtime_state_path(args.state)
        if args.command == "scan":
            result = scan(_read_batch(Path(args.batch)), state_path)
        else:
            result = resolve(args.id, args.digest, args.outcome, args.evidence_hash, state_path)
    except (OSError, UnicodeError, json.JSONDecodeError, RadarError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
