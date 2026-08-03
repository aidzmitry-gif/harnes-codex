"""Validate the version 1 Goal Runner execution passport."""

from __future__ import annotations

import json
import sys
from pathlib import Path


CHAIN_STATUSES = {"planning", "approved", "running", "verifying", "awaiting-user-review", "complete", "blocked"}
SUBGOAL_STATUSES = {"planned", "ready", "running", "done", "blocked", "skipped"}
AGENT_STATUSES = {"planned", "orienting", "active", "done", "blocked"}
EXECUTABLE_CHAIN_STATUSES = {"approved", "running", "verifying", "awaiting-user-review", "complete"}
AUTH_SCOPES = {"successor creation", "bounded continuation", "both"}


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
        if not isinstance(item.get("ownedPaths"), list) or any(not isinstance(path, str) or not path for path in item.get("ownedPaths", [])):
            fail("SUBGOAL_PATHS", f"subgoals[{index}].ownedPaths must be an array of nonempty strings")

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
    verified = chain.get("currentVerifiedSubgoal")
    if "currentVerifiedSubgoal" not in chain or verified is not None and (not isinstance(verified, str) or verified not in by_id or by_id[verified].get("status") not in {"done", "skipped"}):
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
        if item.get("status") in {"orienting", "active"}:
            active_count += 1
        if item.get("writer") and item.get("status") in {"orienting", "active"}:
            worktree, paths = item.get("worktree"), item.get("ownedPaths")
            if not isinstance(worktree, str) or not worktree.strip() or not isinstance(paths, list) or not paths or any(not isinstance(path, str) or not path for path in paths):
                fail("WRITER_OWNERSHIP", f"writer {identifier or index} requires a worktree and owned paths")
            else:
                active_writers.append((worktree.replace("/", "\\").rstrip("\\").lower(), [path.replace("/", "\\").rstrip("\\").lower() for path in paths], identifier or str(index)))
    if isinstance(chain.get("globalAgentCap"), int) and active_count > chain["globalAgentCap"]:
        fail("AGENT_CAP", "active and orienting agents exceed globalAgentCap")
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
