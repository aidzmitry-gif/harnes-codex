"""Plan the next read-only Goal Runner actions from a validated passport."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from goal_runner_validator import validate_passport


ACTION_PRIORITY = {"verify": 0, "wait": 1, "hold": 2, "launch": 3, "complete": 4}
ACTIVE_AGENT_STATUSES = {"orienting", "active"}
TERMINAL_SUBGOAL_STATUSES = {"done", "skipped"}


def _action(action: str, subgoal_id: str | None, agent_id: str | None, reason: str, **details: Any) -> dict[str, Any]:
    return {"action": action, "subgoalId": subgoal_id, "agentId": agent_id, "reason": reason, **details}


def _action_key(item: dict[str, Any], waves: dict[str, int]) -> tuple[int, int, str, str]:
    return (
        ACTION_PRIORITY[item["action"]],
        waves[item["subgoalId"]] if item["action"] == "launch" else 0,
        item["subgoalId"] or "",
        item["agentId"] or "",
    )


def plan_actions(passport: object, parent_state: str) -> dict[str, Any]:
    """Return a deterministic, bounded plan without mutating *passport*."""
    if parent_state not in {"running", "paused", "blocked"}:
        raise ValueError("parent state must be running, paused, or blocked")
    try:
        failures = validate_passport(passport)
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError("passport validation failed for malformed nested data") from exc
    if failures:
        raise ValueError("passport is invalid: " + ", ".join(code for code, _ in failures))

    assert isinstance(passport, dict)
    chain = passport["chain"]
    subgoals = passport["subgoals"]
    agents = passport["agents"]
    assert isinstance(chain, dict) and isinstance(subgoals, list) and isinstance(agents, list)
    effective_parent_state = "blocked" if chain["status"] == "blocked" else parent_state
    blocked_reason = "chain_blocked" if chain["status"] == "blocked" else "parent_blocked"
    executable_chain = chain["status"] in {"approved", "running"}
    continuation_authorized = chain["standingChainAuthorization"] == "approved" and chain["standingAuthorizationScope"] in {"bounded continuation", "both"}

    by_subgoal = {item["id"]: item for item in subgoals}
    agents_by_subgoal: dict[str, list[dict[str, Any]]] = {identifier: [] for identifier in by_subgoal}
    for agent in agents:
        agents_by_subgoal[agent["subgoalId"]].append(agent)

    blocked = {item["id"] for item in subgoals if item["status"] == "blocked"}
    blocked.update(agent["subgoalId"] for agent in agents if agent["status"] == "blocked")
    direct_blocked = set(blocked)
    # Validated waves follow every dependency, so one ordered pass closes the DAG.
    for item in sorted(subgoals, key=lambda item: (item["wave"], item["id"])):
        if any(dependency in blocked for dependency in item["dependsOn"]):
            blocked.add(item["id"])

    active = sum(agent["status"] in ACTIVE_AGENT_STATUSES for agent in agents)
    cap = chain["globalAgentCap"]
    actions: list[dict[str, Any]] = []

    for agent in agents:
        subgoal_id = agent["subgoalId"]
        if agent["status"] == "done" and by_subgoal[subgoal_id]["status"] not in TERMINAL_SUBGOAL_STATUSES:
            actions.append(_action("verify", subgoal_id, agent["id"], "agent_done"))

    for agent in agents:
        if agent["status"] not in ACTIVE_AGENT_STATUSES:
            continue
        subgoal_id = agent["subgoalId"]
        if effective_parent_state == "paused":
            actions.append(_action("hold", subgoal_id, agent["id"], "parent_paused"))
        elif effective_parent_state == "blocked":
            actions.append(_action("hold", subgoal_id, agent["id"], blocked_reason))
        elif subgoal_id in blocked:
            reason = "subgoal_blocked" if subgoal_id in direct_blocked else "dependency_blocked"
            actions.append(_action("hold", subgoal_id, agent["id"], reason))
        else:
            actions.append(_action("wait", subgoal_id, agent["id"], "agent_active"))

    for agent in agents:
        if agent["status"] == "blocked":
            actions.append(_action("hold", agent["subgoalId"], agent["id"], "agent_blocked"))
    for subgoal in subgoals:
        if subgoal["id"] in blocked and subgoal["status"] not in TERMINAL_SUBGOAL_STATUSES and not any(action["action"] == "hold" and action["subgoalId"] == subgoal["id"] for action in actions):
            reason = "subgoal_blocked" if subgoal["id"] in direct_blocked else "dependency_blocked"
            actions.append(_action("hold", subgoal["id"], None, reason))

    if effective_parent_state == "running" and executable_chain and continuation_authorized:
        available = cap - active
        ready = sorted(
            (item for item in subgoals if item["status"] == "ready" and item["id"] not in blocked and not any(agent["status"] in ACTIVE_AGENT_STATUSES | {"blocked", "done"} for agent in agents_by_subgoal[item["id"]])),
            key=lambda item: (item["wave"], item["id"]),
        )
        occupied = {
            agent["worktree"].casefold() if isinstance(agent["worktree"], str) else None
            for agent in agents
            if agent["writer"] and agent["status"] in ACTIVE_AGENT_STATUSES | {"blocked"}
        }
        occupied.update(
            item["worktree"].casefold() if item["worktree"] is not None else None
            for item in subgoals
            if item["execution"] == "primary" and item["status"] == "running" and item["ownedPaths"]
        )
        for subgoal in ready:
            if available <= 0:
                break
            worktree = subgoal["worktree"].casefold() if subgoal["worktree"] is not None else None
            if subgoal["ownedPaths"] and worktree in occupied:
                actions.append(_action("hold", subgoal["id"], None, "worktree_busy"))
                continue
            actions.append(
                _action(
                    "launch",
                    subgoal["id"],
                    None,
                    "ready",
                    execution=subgoal["execution"],
                    model=subgoal["model"],
                    worktree=subgoal["worktree"],
                    ownedPaths=subgoal["ownedPaths"],
                )
            )
            available -= 1
            if subgoal["ownedPaths"]:
                occupied.add(worktree)

    if not actions and all(item["status"] in TERMINAL_SUBGOAL_STATUSES for item in subgoals) and not active:
        actions.append(_action("complete", None, None, "all_subgoals_terminal"))
    elif not actions:
        if not executable_chain:
            reason = blocked_reason if chain["status"] == "blocked" else "chain_status_not_executable"
        elif not continuation_authorized:
            reason = "chain_authorization_not_continuable"
        else:
            reason = "parent_paused" if effective_parent_state == "paused" else blocked_reason if effective_parent_state == "blocked" else "no_actionable_subgoal"
        actions.append(_action("hold", None, None, reason))

    waves = {subgoal["id"]: subgoal["wave"] for subgoal in subgoals}
    return {
        "schemaVersion": 1,
        "chainId": chain["chainId"],
        "parentState": effective_parent_state,
        "capacity": {"cap": cap, "active": active, "available": cap - active},
        "actions": sorted(actions, key=lambda item: _action_key(item, waves)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goal_orchestrator.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("passport")
    plan.add_argument("--parent-state", choices=("running", "paused", "blocked"), required=True)
    args = parser.parse_args(argv)
    try:
        passport = json.loads(Path(args.passport).read_text(encoding="utf-8"))
        result = plan_actions(passport, args.parent_state)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL INPUT: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
