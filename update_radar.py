#!/usr/bin/env python3
"""Single-writer tracker: discovery is separate from local evaluation attestations.

Callers must serialize scan/defer/resolve for each state file. Atomic replacement
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
STATE_VERSION = 3
MAX_BATCH = 64
MAX_SEEN = 4096
MAX_INPUT_BYTES = 1_000_000
MAX_ASSESSMENTS = 16
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


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise RadarError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _decode_json(value: str) -> object:
    if len(value.encode("utf-8")) > MAX_INPUT_BYTES:
        raise RadarError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return json.loads(value, object_pairs_hook=_unique_object)
    except RecursionError as exc:
        raise RadarError("JSON input is nested too deeply") from exc


def _text(value: object, context: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value) <= 500 or value != value.strip()
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise RadarError(f"{context} must be a single-line string of 1..500 characters without controls")


def _evidence(value: object) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise RadarError("evidence must contain 1..8 unique bounded strings")
    for item in value:
        _text(item, "evidence entry")
    if len(set(value)) != len(value):
        raise RadarError("evidence entries must be unique")


def _prerequisites(value: object) -> None:
    if not isinstance(value, dict) or not 1 <= len(value) <= 16:
        raise RadarError("prerequisites must contain 1..16 bounded key/value pairs")
    for key, item in value.items():
        if not isinstance(key, str) or not update_impact.IDENTIFIER.fullmatch(key):
            raise RadarError("prerequisite key must be a bounded lowercase identifier")
        _text(item, "prerequisite value")


def _validate_assessment(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "evidence", "blocker", "recheckWhen", "prerequisites"}:
        raise RadarError("assessment must contain exactly schemaVersion, evidence, blocker, recheckWhen and prerequisites")
    _exact_schema_version(value["schemaVersion"], "assessment")
    _evidence(value["evidence"])
    _text(value["blocker"], "assessment.blocker")
    _text(value["recheckWhen"], "assessment.recheckWhen")
    _prerequisites(value["prerequisites"])


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"schemaVersion": STATE_VERSION, "seen": {}, "evaluations": {}}
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise RadarError(f"state exceeds {MAX_INPUT_BYTES} bytes")
        state = _decode_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RadarError(f"state is unreadable: {exc}") from exc
    if not isinstance(state, dict):
        raise RadarError("state must be an object")
    version = state.get("schemaVersion")
    if type(version) is not int or version not in (1, 2, STATE_VERSION):
        raise RadarError("state.schemaVersion must be integer 1, 2 or 3")
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
    normalized = {}
    evaluation_fields = {"classification", "resolution"}
    if version == STATE_VERSION:
        evaluation_fields |= {"candidate", "assessments"}
    for identifier, evaluation in evaluations.items():
        if not isinstance(evaluation, dict) or set(evaluation) != evaluation_fields:
            raise RadarError(f"state.evaluations[{identifier}] has invalid fields")
        classification = evaluation["classification"]
        if not isinstance(classification, str) or classification not in {"significant", "evaluate", "ignore"}:
            raise RadarError("evaluation classification is invalid")
        resolution = evaluation["resolution"]
        if resolution is not None:
            if classification == "ignore":
                raise RadarError("ignored candidates cannot have a resolution")
            _validate_resolution(resolution, legacy=version < STATE_VERSION)
            if version < STATE_VERSION:
                resolution = {**resolution, "evidence": None}
        candidate = evaluation.get("candidate")
        if candidate is not None:
            try:
                valid = update_impact.validate_candidate(candidate)
            except update_impact.CandidateError as exc:
                raise RadarError(f"stored candidate is invalid: {exc}") from exc
            if valid["id"] != identifier or _digest(candidate) != seen[identifier]:
                raise RadarError("stored candidate does not match observed id/digest")
        assessments = evaluation.get("assessments", [])
        if not isinstance(assessments, list) or len(assessments) > MAX_ASSESSMENTS:
            raise RadarError(f"assessments must contain 0..{MAX_ASSESSMENTS} checkpoints")
        if classification == "ignore" and assessments:
            raise RadarError("ignored candidates cannot have assessments")
        for assessment in assessments:
            _validate_assessment(assessment)
        normalized[identifier] = {"classification": classification, "resolution": resolution,
                                  "candidate": candidate, "assessments": assessments}
    # Missing metadata is legacy-unknown, never an inferred successful evaluation.
    # Conversion stays in memory until a valid observation or resolution changes state.
    return {"schemaVersion": STATE_VERSION, "seen": seen, "evaluations": normalized}


def _validate_resolution(resolution: object, *, legacy: bool = False) -> None:
    fields = {"outcome", "evidenceHash"} if legacy else {"outcome", "evidenceHash", "evidence"}
    if not isinstance(resolution, dict) or set(resolution) != fields:
        raise RadarError("resolution has invalid fields for its state version")
    outcome = resolution["outcome"]
    if not isinstance(outcome, str) or outcome not in {"useful", "no-benefit"}:
        raise RadarError("resolution outcome must be useful or no-benefit")
    if not isinstance(resolution["evidenceHash"], str) or not SHA256.fullmatch(resolution["evidenceHash"]):
        raise RadarError("resolution evidenceHash must be a lowercase SHA-256 digest")
    if not legacy and resolution["evidence"] is not None:
        _evidence(resolution["evidence"])


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
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _pending_summary(state: dict, prerequisites: dict | None = None) -> dict:
    pending = []
    for identifier, item in sorted(state["evaluations"].items()):
        if item["classification"] == "ignore" or item["resolution"] is not None:
            continue
        latest = item["assessments"][-1] if item["assessments"] else None
        reason = "not-assessed"
        if latest is not None:
            required = latest["prerequisites"]
            if prerequisites is None:
                reason = "prerequisites-unknown"
            elif not required.keys() <= prerequisites.keys():
                reason = "prerequisites-missing"
            elif any(prerequisites[key] != value for key, value in required.items()):
                reason = "prerequisites-changed"
            else:
                reason = "prerequisites-unchanged"
        pending.append({"id": identifier, "digest": state["seen"][identifier],
                        "classification": item["classification"], "candidate": item["candidate"],
                        "assessment": latest, "needsRecheck": reason != "prerequisites-unchanged",
                        "recheckReason": reason})
    eligible = sum(item["needsRecheck"] for item in pending)
    return {"pending": pending, "pendingCount": len(pending), "needsRecheckCount": eligible,
            "deferredCount": len(pending) - eligible,
            "unknownEvaluationCount": len(state["seen"]) - len(state["evaluations"])}


def pending(state_path: Path, prerequisites: dict | None = None) -> dict:
    """Read durable facts/checkpoints; compare only observed prerequisite values, never write."""
    if prerequisites is not None:
        _prerequisites(prerequisites)
    state = _load_state(state_path)
    summary = _pending_summary(state, prerequisites)
    return {"schemaVersion": SCHEMA_VERSION, **summary, "stateCount": len(state["seen"]), "stateChanged": False}


def scan(batch: object, state_path: Path) -> dict[str, object]:
    """Observe candidates; pending work survives exact repeats and empty batches."""
    validated = _validate_batch(batch)
    state = _load_state(state_path)
    seen, evaluations = state["seen"], state["evaluations"]
    additions: dict[str, str] = {}
    new_results = []
    repeated = 0
    changed = False

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
                if evaluations[identifier]["candidate"] is None:
                    evaluations[identifier]["candidate"] = candidate
                    changed = True
                continue
        else:
            additions[identifier] = digest
        new_results.append(classification)
        evaluations[identifier] = {"classification": classification["classification"], "resolution": None,
                                   "candidate": candidate, "assessments": []}
        changed = True

    if len(seen) + len(additions) > MAX_SEEN:
        raise RadarError(f"recording this batch would exceed the {MAX_SEEN}-candidate state limit")

    seen.update(additions)
    summary = _pending_summary(state)
    unknown = summary["unknownEvaluationCount"]
    significant = sum(result["classification"] == "significant" for result in new_results)
    evaluate = sum(result["classification"] == "evaluate" for result in new_results)
    ignored = sum(result["classification"] == "ignore" for result in new_results)
    if significant:
        status = "meaningful-updates"
        message = "Есть обновления с потенциально значимым влиянием на Harness; требуется локальная проверка до внедрения."
    elif evaluate:
        status = "updates-need-evidence"
        message = "Обнаружены новые обновления, но влияние на Harness ещё требует доказательств."
    elif summary["pendingCount"]:
        status = "pending-evaluation"
        message = "Есть незавершённые локальные оценки; новых кандидатов для оценки нет."
    elif unknown:
        status = "evaluation-history-unknown"
        message = "История обнаружения есть, но результаты прежних оценок неизвестны."
    else:
        status = "no-meaningful-updates"
        message = "Значимых обновлений для Harness нет."

    if changed:
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
        **summary,
        "stateChanged": changed,
        "stateCount": len(seen),
    }


def _actionable(state: dict, identifier: str, digest: str) -> dict:
    if not isinstance(identifier, str) or not update_impact.IDENTIFIER.fullmatch(identifier):
        raise RadarError("evaluation id must be a bounded candidate identifier")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise RadarError("evaluation digest must be a lowercase SHA-256 digest")
    if state["seen"].get(identifier) != digest:
        raise RadarError("evaluation id/digest does not match observed history")
    evaluation = state["evaluations"].get(identifier)
    if evaluation is None or evaluation["classification"] == "ignore":
        raise RadarError("evaluation requires an observed actionable candidate")
    return evaluation


def defer(identifier: str, digest: str, assessment: object, state_path: Path) -> dict:
    """Append a bounded blocked checkpoint, not a successful evaluation or an executable plan."""
    _validate_assessment(assessment)
    state = _load_state(state_path)
    evaluation = _actionable(state, identifier, digest)
    if evaluation["resolution"] is not None:
        raise RadarError("resolved candidates cannot acquire deferred assessments")
    history = evaluation["assessments"]
    changed = not history or history[-1] != assessment
    if changed:
        if len(history) >= MAX_ASSESSMENTS:
            raise RadarError(f"assessment history would exceed {MAX_ASSESSMENTS}; do not truncate evidence")
        history.append(assessment)
        _write_state(state_path, state)
    return {"schemaVersion": SCHEMA_VERSION, "status": "evaluation-deferred", "id": identifier,
            "digest": digest, "assessmentHash": _digest(assessment), "stateChanged": changed}


def resolve(identifier: str, digest: str, outcome: str, evidence_hash: str, state_path: Path,
            *, evidence: list[str] | None = None) -> dict:
    """Record a caller's local-evaluation attestation, never adopt an update."""
    resolution = {"outcome": outcome, "evidenceHash": evidence_hash, "evidence": evidence}
    _validate_resolution(resolution)
    state = _load_state(state_path)
    evaluation = _actionable(state, identifier, digest)
    previous = evaluation["resolution"]
    if previous is not None and previous != resolution:
        raise RadarError("resolution conflicts with recorded history; do not rewrite evidence")
    changed = previous is None
    if changed:
        evaluation["resolution"] = resolution
        _write_state(state_path, state)
    return {"schemaVersion": SCHEMA_VERSION, "status": "evaluation-recorded", "id": identifier,
            "digest": digest, "outcome": outcome, "evidenceHash": evidence_hash,
            "evidence": evidence, "stateChanged": changed}


def _read_batch(path: Path) -> object:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise RadarError(f"batch exceeds {MAX_INPUT_BYTES} bytes")
    return _decode_json(path.read_text(encoding="utf-8"))


def _json_argument(value: str) -> object:
    # A bounded stdin option avoids Windows native-command JSON quoting/length limits.
    if value == "-":
        payload = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise RadarError(f"JSON input exceeds {MAX_INPUT_BYTES} bytes")
        # Windows PowerShell UTF8 pipelines include a BOM; do not change payload strings.
        value = payload.decode("utf-8-sig")
    return _decode_json(value)


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
    resolve_parser.add_argument("--evidence-json", help="bounded evidence list, or - for UTF-8 stdin (not secrets/transcripts)")
    defer_parser = commands.add_parser("defer")
    defer_parser.add_argument("id")
    defer_parser.add_argument("--digest", required=True)
    defer_parser.add_argument("--assessment-json", required=True, help="checkpoint JSON, or - for UTF-8 stdin")
    pending_parser = commands.add_parser("pending")
    pending_parser.add_argument("--prerequisites-json", help="observed current key/value map, or - for UTF-8 stdin")
    for subparser in (scan_parser, resolve_parser, defer_parser, pending_parser):
        subparser.add_argument("--state", default=".harness/runtime/update-radar-state.json")
    args = parser.parse_args(argv)
    try:
        state_path = _runtime_state_path(args.state)
        if args.command == "scan":
            result = scan(_read_batch(Path(args.batch)), state_path)
        elif args.command == "pending":
            prerequisites = _json_argument(args.prerequisites_json) if args.prerequisites_json is not None else None
            result = pending(state_path, prerequisites)
        elif args.command == "defer":
            result = defer(args.id, args.digest, _json_argument(args.assessment_json), state_path)
        else:
            evidence = _json_argument(args.evidence_json) if args.evidence_json is not None else None
            result = resolve(args.id, args.digest, args.outcome, args.evidence_hash, state_path, evidence=evidence)
    except (OSError, UnicodeError, json.JSONDecodeError, RadarError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
