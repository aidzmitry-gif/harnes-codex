"""Validate the version 1 Goal Runner execution passport."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import acceptance_gate


CHAIN_STATUSES = {"planning", "approved", "running", "verifying", "awaiting-user-review", "complete", "blocked"}
SUBGOAL_STATUSES = {"planned", "ready", "running", "done", "blocked", "skipped"}
AGENT_STATUSES = {"planned", "orienting", "active", "done", "blocked"}
EXECUTABLE_CHAIN_STATUSES = {"approved", "running", "verifying", "awaiting-user-review", "complete"}
AUTH_SCOPES = {"successor creation", "bounded continuation", "both"}
BOUNDED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/@-]{0,63}$")


def validate_passport(passport: object) -> list[tuple[str, str]]:
    """Return stable, sorted (code, message) validation failures."""
    errors: list[tuple[str, str]] = []

    def fail(code: str, message: str) -> None:
        errors.append((code, message))

    def mapping(value: object, name: str) -> dict | None:
        if not isinstance(value, dict):
            fail("TYPE", f"{name} must be an object")
            return None
        return value

    def text(value: object, name: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            fail("REQUIRED", f"{name} must be a nonempty string")
            return False
        return True

    def portable_relative_path(
        value: object,
        name: str,
        *,
        required_prefix: tuple[str, ...] = (),
        suffix: str | None = None,
    ) -> tuple[str, ...] | None:
        """Validate a normalized, repository-relative path and return comparable parts."""
        if not isinstance(value, str) or not value.strip():
            return None
        if value != value.strip() or "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            fail("PATH_SAFETY", f"{name} must be a normalized portable relative path")
            return None
        raw_parts = value.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            fail("PATH_SAFETY", f"{name} must not contain empty, current, or parent path segments")
            return None
        parts = tuple(part.lower() for part in raw_parts)
        if required_prefix and parts[:len(required_prefix)] != required_prefix:
            fail("PATH_SAFETY", f"{name} must stay under {'/'.join(required_prefix)}")
            return None
        if suffix and not parts[-1].endswith(suffix):
            fail("PATH_SAFETY", f"{name} must end with {suffix}")
            return None
        return parts

    root = mapping(passport, "passport")
    if root is None:
        return sorted(errors)
    if root.get("schemaVersion") != 1:
        fail("SCHEMA_VERSION", "schemaVersion must be 1")
    chain = mapping(root.get("chain"), "chain")
    subgoals = root.get("subgoals")
    agents = root.get("agents")
    if not isinstance(subgoals, list):
        fail("TYPE", "subgoals must be an array")
        subgoals = []
    if not isinstance(agents, list):
        fail("TYPE", "agents must be an array")
        agents = []
    if chain is None:
        return sorted(errors)

    for field in ("chainId", "projectRoot", "dataOwner", "externalSideEffectBoundary", "parentOutcome", "approvalProvenance", "checkoutWorktreePolicy", "nextMinimalSliceAcceptance"):
        text(chain.get(field), f"chain.{field}")
    if chain.get("riskClass") not in {"low", "medium", "high"}:
        fail("CHAIN_RISK", "chain.riskClass must be low, medium, or high")
    if chain.get("status") not in CHAIN_STATUSES:
        fail("CHAIN_STATUS", "chain.status is invalid")
    for field, minimum, maximum in (("planRevision", 1, None), ("globalAgentCap", 1, 12), ("delegationDepthCap", 0, 2)):
        value = chain.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum or (maximum is not None and value > maximum):
            bound = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
            fail("CHAIN_NUMBER", f"chain.{field} must be an integer {bound}")
    approved_revision = chain.get("approvedPassportRevision")
    if isinstance(approved_revision, bool) or not isinstance(approved_revision, int) or approved_revision < 1:
        fail("CHAIN_REVISION", "chain.approvedPassportRevision must be an integer >= 1")
    if chain.get("standingChainAuthorization") not in {"absent", "approved"}:
        fail("CHAIN_AUTH", "chain.standingChainAuthorization must be absent or approved")
    scope = chain.get("standingAuthorizationScope")
    if chain.get("standingChainAuthorization") == "approved":
        if scope not in AUTH_SCOPES:
            fail("CHAIN_AUTH", "approved standing authorization requires a valid scope")
    elif scope is not None:
        fail("CHAIN_AUTH", "absent standing authorization requires a null scope")
    plan_revision = chain.get("planRevision")
    if chain.get("status") in EXECUTABLE_CHAIN_STATUSES and chain.get("approvedPassportRevision") != plan_revision:
        fail("CHAIN_REVISION", "approvedPassportRevision must equal planRevision for executable status")
    if chain.get("status") in EXECUTABLE_CHAIN_STATUSES:
        for field in ("canonicalWorkItemPath", "baselineId", "treatmentId", "metricsPath"):
            text(chain.get(field), f"chain.{field}")
        canonical = chain.get("canonicalWorkItemPath")
        if isinstance(canonical, str):
            portable_relative_path(
                canonical,
                "chain.canonicalWorkItemPath",
                required_prefix=(".harness", "work"),
                suffix=".md",
            )
        baseline, treatment = chain.get("baselineId"), chain.get("treatmentId")
        if not isinstance(baseline, str) or not BOUNDED_ID.fullmatch(baseline) or not isinstance(treatment, str) or not BOUNDED_ID.fullmatch(treatment):
            fail("CHAIN_CONTINUITY", "chain baselineId and treatmentId must be bounded identifiers")
        elif baseline == treatment:
            fail("CHAIN_CONTINUITY", "chain baselineId and treatmentId must differ")
        metrics_path = chain.get("metricsPath")
        if isinstance(metrics_path, str):
            portable_relative_path(
                metrics_path,
                "chain.metricsPath",
                required_prefix=(".harness", "metrics"),
                suffix=".jsonl",
            )
        schema = chain.get("metricsSchemaVersion")
        if isinstance(schema, bool) or schema != 1:
            fail("CHAIN_CONTINUITY", "chain.metricsSchemaVersion must be integer 1")

    by_id: dict[str, dict] = {}
    for index, raw in enumerate(subgoals):
        item = mapping(raw, f"subgoals[{index}]")
        if item is None:
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            fail("SUBGOAL_ID", f"subgoals[{index}].id must be nonempty")
        elif identifier in by_id:
            fail("SUBGOAL_ID", f"duplicate subgoal id: {identifier}")
        else:
            by_id[identifier] = item
        depends = item.get("dependsOn")
        if not isinstance(depends, list) or any(not isinstance(dep, str) for dep in depends) or len(set(depends)) != len(depends):
            fail("SUBGOAL_DEPENDS", f"subgoals[{index}].dependsOn must contain unique string IDs")
        wave = item.get("wave")
        if isinstance(wave, bool) or not isinstance(wave, int) or wave < 1:
            fail("SUBGOAL_WAVE", f"subgoals[{index}].wave must be a positive integer")
        if item.get("status") not in SUBGOAL_STATUSES:
            fail("SUBGOAL_STATUS", f"subgoals[{index}].status is invalid")
        if item.get("execution") not in {"primary", "subagent", "task"}:
            fail("SUBGOAL_EXECUTION", f"subgoals[{index}].execution is invalid")
        if item.get("model") not in {"terra", "sol"}:
            fail("SUBGOAL_MODEL", f"subgoals[{index}].model is invalid")
        if "worktree" not in item or item.get("worktree") is not None and not isinstance(item.get("worktree"), str):
            fail("SUBGOAL_WORKTREE", f"subgoals[{index}].worktree must be string or null")
        elif isinstance(item.get("worktree"), str):
            portable_relative_path(item["worktree"], f"subgoals[{index}].worktree")
        if not isinstance(item.get("ownedPaths"), list) or any(not isinstance(path, str) or not path for path in item.get("ownedPaths", [])):
            fail("SUBGOAL_PATHS", f"subgoals[{index}].ownedPaths must be an array of nonempty strings")
        elif isinstance(item.get("ownedPaths"), list):
            for path_index, path in enumerate(item["ownedPaths"]):
                portable_relative_path(path, f"subgoals[{index}].ownedPaths[{path_index}]")
        unlock = item.get("unlockEvidence")
        if unlock is not None:
            if not isinstance(unlock, dict):
                fail("UNLOCK_EVIDENCE", f"subgoals[{index}].unlockEvidence must be an object")
            else:
                work_item, criterion_id = unlock.get("workItem"), unlock.get("criterionId")
                if not isinstance(work_item, str) or not work_item.replace("-", "").replace("_", "").isalnum():
                    fail("UNLOCK_EVIDENCE", f"subgoals[{index}].unlockEvidence.workItem is invalid")
                if not isinstance(criterion_id, str) or not BOUNDED_ID.fullmatch(criterion_id):
                    fail("UNLOCK_EVIDENCE", f"subgoals[{index}].unlockEvidence.criterionId is invalid")

    def dependencies(item: dict) -> list[str]:
        return item.get("dependsOn") if isinstance(item.get("dependsOn"), list) else []

    for identifier, item in by_id.items():
        for dependency in dependencies(item):
            if dependency not in by_id:
                fail("SUBGOAL_DEPENDS", f"{identifier} depends on unknown subgoal {dependency}")
                continue
            if isinstance(item.get("wave"), int) and isinstance(by_id[dependency].get("wave"), int) and item["wave"] <= by_id[dependency]["wave"]:
                fail("SUBGOAL_WAVE", f"{identifier} must have a later wave than {dependency}")
        if item.get("status") in {"ready", "running"}:
            unfinished = [dep for dep in dependencies(item) if dep in by_id and by_id[dep].get("status") not in {"done", "skipped"}]
            if unfinished:
                fail("SUBGOAL_READY", f"{identifier} has unfinished dependencies: {', '.join(sorted(unfinished))}")
            unlock = item.get("unlockEvidence")
            if isinstance(unlock, dict) and isinstance(unlock.get("workItem"), str) and isinstance(unlock.get("criterionId"), str):
                skipped = [dep for dep in dependencies(item) if dep in by_id and by_id[dep].get("status") == "skipped" and (not isinstance(by_id[dep].get("skipReason"), str) or not by_id[dep]["skipReason"].strip())]
                if skipped:
                    fail("SUBGOAL_SKIP_REASON", f"{identifier} has skipped dependencies without skipReason: {', '.join(sorted(skipped))}")
                try:
                    fresh, note = acceptance_gate.stored_evidence_is_fresh(unlock["workItem"], unlock["criterionId"])
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    fresh, note = False, str(exc)
                if not fresh:
                    fail("UNLOCK_EVIDENCE", f"{identifier} unlock evidence is not fresh: {note}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            fail("SUBGOAL_CYCLE", f"dependency cycle includes {identifier}")
            return
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in dependencies(by_id[identifier]):
            if dependency in by_id:
                visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in sorted(by_id):
        visit(identifier)
    if chain.get("status") == "complete":
        unfinished = sorted(identifier for identifier, item in by_id.items() if item.get("status") not in {"done", "skipped"})
        if unfinished:
            fail("CHAIN_COMPLETE", "complete chain has unfinished subgoals: " + ", ".join(unfinished))
    verified = chain.get("currentVerifiedSubgoal")
    if (
        "currentVerifiedSubgoal" not in chain
        or chain.get("standingChainAuthorization") == "approved" and verified is None
        or verified is not None and (not isinstance(verified, str) or verified not in by_id or by_id[verified].get("status") not in {"done", "skipped"})
    ):
        fail("CHAIN_VERIFIED", "currentVerifiedSubgoal must name a done or skipped subgoal")

    active_writers: list[tuple[str, list[str], str]] = []
    agent_ids: set[str] = set()
    active_count = 0
    for index, raw in enumerate(agents):
        item = mapping(raw, f"agents[{index}]")
        if item is None:
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in agent_ids:
            fail("AGENT_ID", f"agents[{index}].id must be unique and nonempty")
        else:
            agent_ids.add(identifier)
        if item.get("subgoalId") not in by_id:
            fail("AGENT_SUBGOAL", f"agents[{index}].subgoalId must name a known subgoal")
        text(item.get("role"), f"agents[{index}].role")
        depth = item.get("depth")
        if isinstance(depth, bool) or not isinstance(depth, int) or depth < 0 or isinstance(chain.get("delegationDepthCap"), int) and depth > chain["delegationDepthCap"]:
            fail("AGENT_DEPTH", f"agents[{index}].depth exceeds delegation depth cap")
        if item.get("status") not in AGENT_STATUSES:
            fail("AGENT_STATUS", f"agents[{index}].status is invalid")
        if not isinstance(item.get("writer"), bool):
            fail("AGENT_WRITER", f"agents[{index}].writer must be boolean")
        agent_worktree = item.get("worktree")
        if isinstance(agent_worktree, str):
            portable_relative_path(agent_worktree, f"agents[{index}].worktree")
        agent_paths = item.get("ownedPaths")
        if isinstance(agent_paths, list):
            for path_index, path in enumerate(agent_paths):
                portable_relative_path(path, f"agents[{index}].ownedPaths[{path_index}]")
        if item.get("status") in {"orienting", "active"}:
            active_count += 1
        if item.get("writer") and item.get("status") in {"orienting", "active"}:
            worktree, paths = item.get("worktree"), item.get("ownedPaths")
            if not isinstance(worktree, str) or not worktree.strip() or not isinstance(paths, list) or not paths or any(not isinstance(path, str) or not path for path in paths):
                fail("WRITER_OWNERSHIP", f"writer {identifier or index} requires a worktree and owned paths")
            else:
                normalized_worktree = portable_relative_path(worktree, f"agents[{index}].worktree")
                normalized_paths = [portable_relative_path(path, f"agents[{index}].ownedPaths[{path_index}]") for path_index, path in enumerate(paths)]
                subgoal = by_id.get(item.get("subgoalId"), {})
                expected_worktree = subgoal.get("worktree")
                expected_paths = subgoal.get("ownedPaths")
                normalized_expected_worktree = portable_relative_path(expected_worktree, f"subgoals[{item.get('subgoalId')}].worktree")
                normalized_expected = [
                    portable_relative_path(path, f"subgoals[{item.get('subgoalId')}].ownedPaths[{path_index}]")
                    for path_index, path in enumerate(expected_paths)
                ] if isinstance(expected_paths, list) else []
                paths_within_scope = bool(normalized_paths) and all(
                    path is not None and any(
                        root is not None and (path == root or path[:len(root)] == root)
                        for root in normalized_expected
                    )
                    for path in normalized_paths
                )
                if normalized_worktree is None or normalized_worktree != normalized_expected_worktree or not paths_within_scope:
                    fail("AGENT_OWNERSHIP", f"writer {identifier or index} must stay within its subgoal worktree and owned paths")
                if normalized_worktree is not None:
                    active_writers.append(("/".join(normalized_worktree), ["/".join(path) for path in normalized_paths if path is not None], identifier or str(index)))
    if isinstance(chain.get("globalAgentCap"), int) and active_count > chain["globalAgentCap"]:
        fail("AGENT_CAP", "active and orienting agents exceed globalAgentCap")
    if chain.get("status") == "complete" and active_count:
        fail("CHAIN_COMPLETE", "complete chain cannot have active or orienting agents")
    for position, (worktree, paths, identifier) in enumerate(active_writers):
        for other_worktree, other_paths, other_identifier in active_writers[position + 1:]:
            if worktree == other_worktree:
                fail("WRITER_CONFLICT", f"active writers {identifier} and {other_identifier} share worktree {worktree}")

    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "check":
        print("usage: goal_runner_validator.py check FILE", file=sys.stderr)
        return 2
    try:
        passport = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL INPUT: {exc}")
        return 2
    errors = validate_passport(passport)
    if errors:
        for code, message in errors:
            print(f"FAIL {code}: {message}")
        return 2
    print("PASS goal passport is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
