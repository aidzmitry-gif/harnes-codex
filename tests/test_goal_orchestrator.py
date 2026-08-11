import copy
import hashlib
import json
import subprocess
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from goal_orchestrator import main, plan_actions
from tests.test_goal_runner_validator import valid_passport


class GoalOrchestratorTests(unittest.TestCase):
    def passport(self):
        passport = valid_passport()
        passport["agents"] = []
        return passport

    def test_running_parent_launches_ready_subgoal_with_passport_details(self):
        passport = self.passport()

        result = plan_actions(passport, "running")

        self.assertEqual(2, result["capacity"]["cap"])
        self.assertEqual(0, result["capacity"]["active"])
        self.assertEqual(2, result["capacity"]["available"])
        self.assertEqual(
            [{"action": "launch", "subgoalId": "G02", "agentId": None, "reason": "ready", "execution": "subagent", "model": "terra", "worktree": "g02", "ownedPaths": ["x.py"]}],
            result["actions"],
        )

    def test_launches_are_ordered_by_wave_before_subgoal_id(self):
        passport = self.passport()
        passport["subgoals"][1].update({"id": "Z", "wave": 2})
        passport["subgoals"].append({"id": "A", "dependsOn": ["G01"], "wave": 3, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "a", "ownedPaths": ["a.py"]})

        result = plan_actions(passport, "running")

        self.assertEqual(["Z", "A"], [action["subgoalId"] for action in result["actions"]])

    def test_invalid_passport_fails_closed(self):
        passport = self.passport()
        passport["chain"]["riskClass"] = "invalid"

        with self.assertRaises(ValueError):
            plan_actions(passport, "running")

    def test_cli_fails_closed_for_unreadable_and_malformed_input(self):
        with patch("sys.stderr", new_callable=StringIO):
            self.assertEqual(2, main(["plan", "missing.json", "--parent-state", "running"]))
        with patch("goal_orchestrator.Path.read_text", side_effect=json.JSONDecodeError("bad", "{", 0)), patch("sys.stderr", new_callable=StringIO):
            self.assertEqual(2, main(["plan", "passport.json", "--parent-state", "running"]))

    def test_cap_and_duplicate_active_work_suppress_launch(self):
        passport = self.passport()
        passport["chain"]["globalAgentCap"] = 1
        passport["subgoals"].append({"id": "G03", "dependsOn": ["G01"], "wave": 3, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g03", "ownedPaths": ["g03.py"]})
        passport["agents"] = [{"id": "a1", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "active", "writer": True}]

        result = plan_actions(passport, "running")

        self.assertEqual(1, result["capacity"]["active"])
        self.assertEqual(["wait"], [action["action"] for action in result["actions"]])
        self.assertNotIn("launch", [action["action"] for action in result["actions"]])

    def test_blocked_agent_and_subgoal_produce_hold(self):
        passport = self.passport()
        passport["subgoals"].append({"id": "G03", "dependsOn": ["G01"], "wave": 3, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g03", "ownedPaths": ["g03.py"]})
        passport["agents"] = [{"id": "a1", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "blocked", "writer": True}]

        result = plan_actions(passport, "running")

        self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
        self.assertEqual("agent_blocked", result["actions"][0]["reason"])
        self.assertNotIn("launch", [action["action"] for action in result["actions"]])

    def test_blocked_subgoal_globally_suppresses_other_ready_launches(self):
        passport = self.passport()
        passport["subgoals"][1]["status"] = "blocked"
        passport["subgoals"].append({"id": "G03", "dependsOn": ["G01"], "wave": 3, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g03", "ownedPaths": ["g03.py"]})

        result = plan_actions(passport, "running")

        self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
        self.assertEqual("subgoal_blocked", result["actions"][0]["reason"])

    def test_non_executable_chain_statuses_hold_without_launch(self):
        for status in ("planning", "verifying", "awaiting-user-review"):
            with self.subTest(status=status):
                passport = self.passport()
                passport["chain"]["status"] = status
                result = plan_actions(passport, "running")
                self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
                self.assertEqual("chain_status_not_executable", result["actions"][0]["reason"])

    def test_authorization_requires_continuation_scope_for_launch(self):
        cases = (("absent", None), ("approved", "successor creation"))
        for authorization, scope in cases:
            with self.subTest(authorization=authorization, scope=scope):
                passport = self.passport()
                passport["chain"].update({"standingChainAuthorization": authorization, "standingAuthorizationScope": scope})
                result = plan_actions(passport, "running")
                self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
                self.assertEqual("chain_authorization_not_continuable", result["actions"][0]["reason"])

        passport = self.passport()
        passport["chain"]["standingAuthorizationScope"] = "bounded continuation"
        self.assertEqual("launch", plan_actions(passport, "running")["actions"][0]["action"])

    def test_blocked_chain_dominates_running_cli_state(self):
        passport = self.passport()
        passport["chain"]["status"] = "blocked"

        result = plan_actions(passport, "running")

        self.assertEqual("blocked", result["parentState"])
        self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
        self.assertEqual("chain_blocked", result["actions"][0]["reason"])

    def test_malformed_nested_passport_fails_closed(self):
        passport = self.passport()
        passport["subgoals"][1]["id"] = []

        with self.assertRaises(ValueError):
            plan_actions(passport, "running")
        with patch("goal_orchestrator.Path.read_text", return_value=json.dumps(passport)), patch("sys.stderr", new_callable=StringIO) as stderr:
            self.assertEqual(2, main(["plan", "passport.json", "--parent-state", "running"]))
        self.assertTrue(stderr.getvalue().startswith("FAIL INPUT:"))

    def test_paused_and_blocked_parents_hold_active_agents_and_never_launch(self):
        passport = self.passport()
        passport["agents"] = [{"id": "a1", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "orienting", "writer": True}]

        for parent_state, reason in (("paused", "parent_paused"), ("blocked", "parent_blocked")):
            with self.subTest(parent_state=parent_state):
                result = plan_actions(passport, parent_state)
                self.assertEqual(["hold"], [action["action"] for action in result["actions"]])
                self.assertEqual(reason, result["actions"][0]["reason"])

    def test_done_agent_requires_verify_and_never_marks_subgoal_done(self):
        passport = self.passport()
        passport["agents"] = [{"id": "a1", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "done", "writer": True}]

        result = plan_actions(passport, "running")

        self.assertEqual("ready", passport["subgoals"][1]["status"])
        self.assertEqual(["verify"], [action["action"] for action in result["actions"]])
        self.assertEqual("a1", result["actions"][0]["agentId"])

    def test_actions_are_ordered_and_byte_identical(self):
        passport = self.passport()
        passport["subgoals"].append({"id": "G03", "dependsOn": ["G01"], "wave": 3, "status": "blocked", "execution": "subagent", "model": "terra", "worktree": "g03", "ownedPaths": ["g03.py"]})
        passport["agents"] = [
            {"id": "z", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "active", "writer": True},
            {"id": "a", "subgoalId": "G03", "role": "worker", "depth": 1, "worktree": "g03", "ownedPaths": ["g03.py"], "status": "done", "writer": True},
        ]
        first = json.dumps(plan_actions(passport, "running"), sort_keys=True, separators=(",", ":"))
        second = json.dumps(plan_actions(copy.deepcopy(passport), "running"), sort_keys=True, separators=(",", ":"))

        self.assertEqual(first, second)
        self.assertEqual(["verify", "wait", "hold"], [action["action"] for action in json.loads(first)["actions"]])

    def test_complete_and_no_actionable_fallbacks(self):
        passport = self.passport()
        passport["subgoals"][1]["status"] = "done"
        complete = plan_actions(passport, "running")
        self.assertEqual(["complete"], [action["action"] for action in complete["actions"]])

        passport = self.passport()
        passport["subgoals"][1]["status"] = "planned"
        hold = plan_actions(passport, "running")
        self.assertEqual("no_actionable_subgoal", hold["actions"][0]["reason"])

    def test_cli_output_is_canonical_and_input_file_is_unchanged(self):
        path = Path("tests/fixtures/valid_goal_passport.json")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        result = subprocess.run(
            [sys.executable, "goal_orchestrator.py", "plan", str(path), "--parent-state", "running"],
            capture_output=True,
            text=True,
            check=False,
        )
        after = hashlib.sha256(path.read_bytes()).hexdigest()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, after)
        self.assertEqual(result.stdout, json.dumps(json.loads(result.stdout), sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    unittest.main()
