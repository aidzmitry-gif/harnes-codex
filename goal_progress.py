#!/usr/bin/env python3
"""Fail closed on repeated, structurally identical Goal Runner attempts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import acceptance_gate
from goal_runner_validator import validate_passport


BOUNDED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/@-]{0,63}$")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
STATE_KEY = "goalProgress"
# ponytail: retain at most 256 unique signatures per passport. If a chain
# genuinely needs more, add a bounded signature index before raising this cap.
MAX_ATTEMPTS = 256


class ProgressError(ValueError):
    """Input or durable state is unsafe to use for a progress decision."""


def fingerprint(value: object) -> dict[str, str]:
    """Validate the safe repository fingerprint shape shared with acceptance_gate."""
    if not isinstance(value, dict) or set(value) != {"algorithm", "status", "value"}:
        raise ProgressError("repository fingerprint must have algorithm, status, and value")
    if value.get("algorithm") != "sha256" or value.get("status") != "ok" or not isinstance(value.get("value"), str) or not FINGERPRINT.fullmatch(value["value"]):
        raise ProgressError("repository fingerprint must be an available sha256")
    return {"algorithm": "sha256", "status": "ok", "value": value["value"]}


def bounded(value: object, name: str) -> str:
    if not isinstance(value, str) or not BOUNDED_ID.fullmatch(value):
        raise ProgressError(f"{name} must be a bounded identifier")
    return value


def stable_digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_fingerprint(unlock: object) -> dict[str, str] | None:
    """Hash stored evidence state without retaining evidence text or running criteria."""
    if unlock is None:
        return None
    if not isinstance(unlock, dict) or set(unlock) != {"workItem", "criterionId"}:
        raise ProgressError("unlockEvidence must contain only workItem and criterionId")
    work_item = unlock["workItem"]
    criterion_id = unlock["criterionId"]
    if not isinstance(work_item, str) or not work_item.replace("-", "").replace("_", "").isalnum():
        raise ProgressError("unlockEvidence.workItem is invalid")
    bounded(criterion_id, "unlockEvidence.criterionId")
    try:
        criteria = acceptance_gate.validate(acceptance_gate.load(acceptance_gate.gate_path(work_item)))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"algorithm": "sha256", "status": "missing", "value": stable_digest({"workItem": work_item, "criterionId": criterion_id, "error": type(exc).__name__})}
    criterion = next((item for item in criteria if item["id"] == criterion_id), None)
    if criterion is None:
        return {"algorithm": "sha256", "status": "missing", "value": stable_digest({"workItem": work_item, "criterionId": criterion_id, "state": "absent"})}
    fresh, _ = acceptance_gate.stored_evidence_is_fresh(work_item, criterion_id)
    try:
        stored_fingerprint = fingerprint(criterion.get("fingerprint"))
    except ProgressError:
        stored_fingerprint = None
    payload = {
        "criterionId": criterion_id,
        "evidencePresent": bool(str(criterion.get("evidence", "")).strip()),
        "fresh": fresh,
        "kind": criterion.get("kind"),
        "passes": criterion.get("passes") is True,
        "storedFingerprint": stored_fingerprint,
        "workItem": work_item,
    }
    return {"algorithm": "sha256", "status": "ok", "value": stable_digest(payload)}


def attempt_signature(passport: object, subgoal_id: str, strategy_id: str) -> dict[str, object]:
    """Build the bounded signature for one attempt using current local state."""
    if not isinstance(passport, dict) or not isinstance(passport.get("chain"), dict):
        raise ProgressError("passport.chain must be an object")
    chain_id = bounded(passport["chain"].get("chainId"), "chain.chainId")
    subgoals = passport.get("subgoals")
    if not isinstance(subgoals, list):
        raise ProgressError("passport.subgoals must be an array")
    matches = [item for item in subgoals if isinstance(item, dict) and item.get("id") == subgoal_id]
    if len(matches) != 1:
        raise ProgressError("subgoal must name exactly one passport subgoal")
    return {
        "chainId": chain_id,
        "subgoalId": bounded(subgoal_id, "subgoal"),
        "strategyId": bounded(strategy_id, "strategy"),
        "repositoryFingerprint": fingerprint(acceptance_gate.fingerprint()),
        "unlockEvidenceFingerprint": evidence_fingerprint(matches[0].get("unlockEvidence")),
    }


def validate_state(passport: dict) -> list[dict[str, object]]:
    """Read only the strict, bounded state owned by this CLI."""
    state = passport.get(STATE_KEY)
    if state is None:
        return []
    if not isinstance(state, dict) or set(state) != {"schemaVersion", "attempts"} or state.get("schemaVersion") != 1 or not isinstance(state.get("attempts"), list):
        raise ProgressError("goalProgress must contain schemaVersion 1 and attempts")
    if len(state["attempts"]) > MAX_ATTEMPTS:
        raise ProgressError(f"goalProgress may contain at most {MAX_ATTEMPTS} attempts")
    attempts: list[dict[str, object]] = []
    for item in state["attempts"]:
        if not isinstance(item, dict) or set(item) != {"chainId", "subgoalId", "strategyId", "repositoryFingerprint", "unlockEvidenceFingerprint"}:
            raise ProgressError("goalProgress attempt has invalid fields")
        for field in ("chainId", "subgoalId", "strategyId"):
            bounded(item[field], f"goalProgress.{field}")
        entry = dict(item)
        entry["repositoryFingerprint"] = fingerprint(item["repositoryFingerprint"])
        evidence = item["unlockEvidenceFingerprint"]
        if evidence is not None:
            if not isinstance(evidence, dict) or set(evidence) != {"algorithm", "status", "value"} or evidence.get("algorithm") != "sha256" or evidence.get("status") not in {"ok", "missing"} or not isinstance(evidence.get("value"), str) or not FINGERPRINT.fullmatch(evidence["value"]):
                raise ProgressError("goalProgress unlock evidence fingerprint is invalid")
            entry["unlockEvidenceFingerprint"] = dict(evidence)
        attempts.append(entry)
    if len({stable_digest(item) for item in attempts}) != len(attempts):
        raise ProgressError("goalProgress attempts must be unique")
    return attempts


def save_atomic(path: Path, passport: dict) -> None:
    """Replace the passport atomically in its current directory."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(json.dumps(passport, ensure_ascii=False, indent=2) + "\n")
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4 or argv[0] not in {"check", "record"}:
        print("usage: goal_progress.py check|record PASSPORT SUBGOAL STRATEGY", file=sys.stderr)
        return 2
    action, file_name, subgoal_id, strategy_id = argv
    try:
        path = Path(file_name)
        passport = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(passport, dict):
            raise ProgressError("passport must be an object")
        if action == "record":
            passport_errors = validate_passport(passport)
            if passport_errors:
                raise ProgressError(f"passport is invalid: {passport_errors[0][0]}")
        attempts = validate_state(passport)
        signature = attempt_signature(passport, subgoal_id, strategy_id)
    except (OSError, json.JSONDecodeError, ProgressError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    if signature in attempts:
        print("NO_PROGRESS identical attempt signature", file=sys.stderr)
        return 1
    if action == "check":
        print("PASS new attempt signature")
        return 0
    passport[STATE_KEY] = {"schemaVersion": 1, "attempts": attempts + [signature]}
    try:
        save_atomic(path, passport)
    except OSError as exc:
        print(f"FAIL SAVE: {exc}", file=sys.stderr)
        return 2
    print("PASS recorded attempt signature")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
