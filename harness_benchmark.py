#!/usr/bin/env python3
"""Run the checked-in deterministic paired Harness contract benchmark."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import acceptance_gate
import harness_metrics
import goal_runner_validator


SCHEMA_VERSION = 1
MODES = ("baseline", "treatment")
SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SAFE_CASES = {
    "telemetry": {
        "valid_unknown_tokens", "missing_required", "one_token_only", "secret_identifier",
        "used_without_release", "zero_attempts", "unknown_field",
    },
    "acceptance": {"fresh_manual", "legacy_manual", "missing_evidence", "stale_manual", "manual_false"},
    "goal": {"valid", "missing_auth_scope", "missing_verified_boundary", "dependency_cycle", "agent_cap", "writer_conflict", "unknown_dependency", "bad_wave"},
}


def _event(**updates: Any) -> dict[str, Any]:
    event = {
        "runId": "safe-run", "pairKey": "safe-pair", "treatment": "baseline", "mode": "benchmark",
        "durationMs": 0, "attempts": 1, "reworkCount": 0, "accepted": True,
        "escapedDefects": 0, "checksPassed": 1, "checksFailed": 0,
        "inputTokens": None, "outputTokens": None,
    }
    event.update(updates)
    return event


def _passport() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "chain": {"chainId": "benchmark", "projectRoot": "D:\\benchmark", "dataOwner": "local", "riskClass": "low", "externalSideEffectBoundary": "none", "parentOutcome": "test", "status": "running", "planRevision": 1, "approvedPassportRevision": 1, "approvalProvenance": "fixture", "checkoutWorktreePolicy": "isolated", "globalAgentCap": 2, "delegationDepthCap": 1, "standingChainAuthorization": "approved", "standingAuthorizationScope": "both", "currentVerifiedSubgoal": "G01", "nextMinimalSliceAcceptance": "test"},
        "subgoals": [
            {"id": "G01", "dependsOn": [], "wave": 1, "status": "done", "execution": "primary", "model": "terra", "worktree": None, "ownedPaths": []},
            {"id": "G02", "dependsOn": ["G01"], "wave": 2, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g02", "ownedPaths": ["x.py"]},
        ],
        "agents": [{"id": "worker", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "active", "writer": True}],
    }


def _telemetry(case: str, mode: str) -> bool:
    changes = {
        "valid_unknown_tokens": {}, "missing_required": {"runId": None}, "one_token_only": {"inputTokens": 1},
        "secret_identifier": {"runId": "token=redacted"}, "used_without_release": {"used": True, "released": False},
        "zero_attempts": {"attempts": 0}, "unknown_field": {"notes": "unsafe"},
    }[case]
    event = _event(**changes)
    if mode == "baseline":
        return isinstance(event, dict) and bool(event.get("mode"))
    try:
        harness_metrics.validate_event(event)
        return True
    except ValueError:
        return False


def _acceptance(case: str, mode: str) -> bool:
    current = {"algorithm": "sha256", "value": "current", "status": "ok"}
    criteria = {
        "fresh_manual": {"id": "manual", "kind": "manual", "passes": True, "evidence": "reviewed", "fingerprint": current},
        "legacy_manual": {"id": "manual", "kind": "manual", "passes": True, "evidence": "reviewed"},
        "missing_evidence": {"id": "manual", "kind": "manual", "passes": True, "evidence": "", "fingerprint": current},
        "stale_manual": {"id": "manual", "kind": "manual", "passes": True, "evidence": "reviewed", "fingerprint": {**current, "value": "stale"}},
        "manual_false": {"id": "manual", "kind": "manual", "passes": False, "evidence": "reviewed", "fingerprint": current},
    }
    criterion = criteria[case]
    if mode == "baseline":
        return bool(criterion.get("passes"))
    original = acceptance_gate.fingerprint
    acceptance_gate.fingerprint = lambda: current
    try:
        return acceptance_gate.evaluate(copy.deepcopy(criterion))[0]
    finally:
        acceptance_gate.fingerprint = original


def _goal(case: str, mode: str) -> bool:
    passport = _passport()
    if case == "missing_auth_scope": passport["chain"]["standingAuthorizationScope"] = None
    elif case == "missing_verified_boundary": passport["chain"]["currentVerifiedSubgoal"] = None
    elif case == "dependency_cycle": passport["subgoals"][0].update({"dependsOn": ["G02"], "wave": 3})
    elif case == "agent_cap": passport["chain"]["globalAgentCap"] = 0
    elif case == "writer_conflict": passport["agents"].append({**passport["agents"][0], "id": "second"})
    elif case == "unknown_dependency": passport["subgoals"][1]["dependsOn"] = ["missing"]
    elif case == "bad_wave": passport["subgoals"][1]["wave"] = 1
    if mode == "baseline":
        return passport.get("schemaVersion") == 1 and isinstance(passport.get("chain"), dict)
    return not goal_runner_validator.validate_passport(passport)


def load_fixture(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid fixture: {exc}") from exc
    if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION or set(data) != {"schemaVersion", "scenarios"}:
        raise ValueError("fixture must use schemaVersion 1 with scenarios only")
    scenarios = data["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) < 20:
        raise ValueError("fixture must contain at least 20 scenarios")
    identifiers: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict) or set(scenario) != {"id", "adapter", "case", "expected"}:
            raise ValueError("fixture scenario has unsafe fields")
        identifier, adapter, case, expected = scenario["id"], scenario["adapter"], scenario["case"], scenario["expected"]
        if not isinstance(identifier, str) or not SAFE_IDENTIFIER.fullmatch(identifier) or identifier in identifiers:
            raise ValueError("fixture scenario IDs must be unique safe identifiers")
        identifiers.add(identifier)
        if adapter not in SAFE_CASES or case not in SAFE_CASES[adapter]:
            raise ValueError("fixture selects an unsafe adapter or case")
        if not isinstance(expected, dict) or set(expected) != set(MODES) or any(not isinstance(expected[item], bool) for item in MODES):
            raise ValueError("fixture expected results must name both modes")
    return scenarios


def _run(scenario: dict[str, Any], mode: str) -> bool:
    return {"telemetry": _telemetry, "acceptance": _acceptance, "goal": _goal}[scenario["adapter"]](scenario["case"], mode)


def run_fixture(path: Path) -> dict[str, Any]:
    scenarios = load_fixture(path)
    records: list[dict[str, Any]] = []
    verdicts = {mode: {"accepted": 0, "rejected": 0} for mode in MODES}
    improvement_cases = 0
    total_duration = 0
    for scenario in scenarios:
        outcomes: dict[str, bool] = {}
        for mode in MODES:
            started = time.monotonic()
            result = _run(scenario, mode)
            outcomes[mode] = result
            verdicts[mode]["accepted" if result else "rejected"] += 1
            duration = max(0, round((time.monotonic() - started) * 1000))
            total_duration += duration
            accepted = result == scenario["expected"][mode]
            records.append(harness_metrics.normalize_event({
                "runId": f"benchmark-{scenario['id']}-{mode}", "pairKey": scenario["id"],
                "chainId": "HRE-001", "subgoalId": "G05", "treatment": mode, "mode": "benchmark",
                "model": None, "reasoningEffort": None, "inputTokens": None, "outputTokens": None,
                "durationMs": duration, "attempts": 1, "reworkCount": 0, "accepted": accepted,
                "released": accepted, "used": accepted, "escapedDefects": 0 if accepted else 1,
                "checksPassed": 1 if accepted else 0, "checksFailed": 0 if accepted else 1,
            }, recorded_at="2026-08-03T00:00:00Z"))
        if outcomes["baseline"] != outcomes["treatment"]:
            improvement_cases += 1
    baseline = [record for record in records if record["treatment"] == "baseline"]
    treatment = [record for record in records if record["treatment"] == "treatment"]
    paired = harness_metrics.compare(records, "baseline", "treatment")
    return {
        "schemaVersion": SCHEMA_VERSION, "scenarioCount": len(scenarios), "pairCount": paired["pairs"],
        "quality": {"baseline": harness_metrics.summary(baseline), "treatment": harness_metrics.summary(treatment)},
        "objectiveVerdicts": {"baseline": verdicts["baseline"], "treatment": verdicts["treatment"], "contractChangeCases": improvement_cases},
        "comparison": paired,
        "tokenEvidence": {"status": "unknown-no-model-runtime", "knownRuns": 0, "coverage": 0.0, "delta": None},
        "measurement": {"durationMs": total_duration, "note": "Measured wall duration may vary; it is not a logical benchmark result."},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run_fixture(args.fixture), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True, separators=(",", ":")), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
