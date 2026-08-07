import copy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from goal_runner_validator import validate_passport


def valid_passport():
    return {
        "schemaVersion": 1,
        "chain": {"chainId": "HRE-001", "projectRoot": "D:\\repo", "dataOwner": "team", "riskClass": "medium", "externalSideEffectBoundary": "local only", "parentOutcome": "validate", "status": "running", "planRevision": 1, "approvedPassportRevision": 1, "approvalProvenance": "task", "canonicalWorkItemPath": ".harness/work/hre-001.md", "checkoutWorktreePolicy": "isolated", "globalAgentCap": 2, "delegationDepthCap": 1, "standingChainAuthorization": "approved", "standingAuthorizationScope": "both", "currentVerifiedSubgoal": "G01", "nextMinimalSliceAcceptance": "test", "baselineId": "baseline", "treatmentId": "treatment", "metricsPath": ".harness/metrics/hre-001.jsonl", "metricsSchemaVersion": 1},
        "subgoals": [
            {"id": "G01", "dependsOn": [], "wave": 1, "status": "done", "execution": "primary", "model": "terra", "worktree": None, "ownedPaths": []},
            {"id": "G02", "dependsOn": ["G01"], "wave": 2, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g02", "ownedPaths": ["x.py"]},
        ],
        "agents": [{"id": "a1", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "active", "writer": True}],
    }


class GoalPassportValidationTests(unittest.TestCase):
    def assert_code(self, passport, code):
        self.assertIn(code, [failure[0] for failure in validate_passport(passport)])

    def test_valid_plan_is_accepted(self):
        self.assertEqual([], validate_passport(valid_passport()))

    def test_missing_authorization_is_rejected(self):
        passport = valid_passport(); passport["chain"]["standingAuthorizationScope"] = None
        self.assert_code(passport, "CHAIN_AUTH")

    def test_approved_authorization_requires_verified_boundary(self):
        passport = valid_passport(); passport["chain"]["currentVerifiedSubgoal"] = None
        self.assert_code(passport, "CHAIN_VERIFIED")

    def test_executable_plan_requires_measurement_continuity(self):
        passport = valid_passport()
        for field in ("canonicalWorkItemPath", "baselineId", "treatmentId", "metricsPath", "metricsSchemaVersion"):
            passport["chain"].pop(field)
        codes = [failure[0] for failure in validate_passport(passport)]
        self.assertIn("CHAIN_CONTINUITY", codes)
        self.assertIn("REQUIRED", codes)

    def test_goal_progress_is_validated_as_bounded_machine_state(self):
        passport = valid_passport()
        passport["goalProgress"] = {"schemaVersion": 1, "attempts": [{"transcript": "free text"}]}
        self.assert_code(passport, "GOAL_PROGRESS")
        passport["goalProgress"] = {"schemaVersion": 1.0, "attempts": []}
        self.assert_code(passport, "GOAL_PROGRESS")

    def test_duplicate_and_unknown_dependencies_are_rejected(self):
        passport = valid_passport(); passport["subgoals"][1]["dependsOn"] = ["missing", "missing"]
        self.assert_code(passport, "SUBGOAL_DEPENDS")

    def test_cycles_are_rejected(self):
        passport = valid_passport(); passport["subgoals"][0].update({"dependsOn": ["G02"], "wave": 3})
        self.assert_code(passport, "SUBGOAL_CYCLE")

    def test_incorrect_ready_wave_is_rejected(self):
        passport = valid_passport(); passport["subgoals"][1]["wave"] = 1
        self.assert_code(passport, "SUBGOAL_WAVE")

    @patch("goal_runner_validator.acceptance_gate.stored_evidence_is_fresh", return_value=(True, "fresh"))
    def test_ready_subgoal_accepts_fresh_unlock_evidence(self, _):
        passport = valid_passport(); passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        self.assertEqual([], validate_passport(passport))

    @patch("goal_runner_validator.acceptance_gate.stored_evidence_is_fresh", return_value=(False, "stale stored acceptance evidence"))
    def test_ready_subgoal_rejects_missing_or_stale_unlock_evidence(self, _):
        passport = valid_passport(); passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        self.assert_code(passport, "UNLOCK_EVIDENCE")

    @patch("goal_runner_validator.acceptance_gate.stored_evidence_is_fresh", return_value=(True, "fresh"))
    def test_evidence_bound_skipped_dependency_requires_reason(self, _):
        passport = valid_passport(); passport["subgoals"][0]["status"] = "skipped"; passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        self.assert_code(passport, "SUBGOAL_SKIP_REASON")
        passport["subgoals"][0]["skipReason"] = "  "
        self.assert_code(passport, "SUBGOAL_SKIP_REASON")
        passport["subgoals"][0]["skipReason"] = "owner-approved"
        self.assertEqual([], validate_passport(passport))

    def test_cap_and_depth_excess_are_rejected(self):
        passport = valid_passport(); passport["chain"]["globalAgentCap"] = 1; passport["agents"].append(copy.deepcopy(passport["agents"][0])); passport["agents"][1].update({"id": "a2", "depth": 2, "worktree": "g03"})
        codes = [failure[0] for failure in validate_passport(passport)]
        self.assertIn("AGENT_CAP", codes); self.assertIn("AGENT_DEPTH", codes)

    def test_writer_conflict_is_rejected(self):
        passport = valid_passport(); passport["agents"].append({"id": "a2", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["other.py"], "status": "orienting", "writer": True})
        self.assert_code(passport, "WRITER_CONFLICT")

    def test_writer_must_match_subgoal_ownership(self):
        passport = valid_passport(); passport["agents"][0].update({"worktree": "different", "ownedPaths": ["outside.py"]})
        self.assert_code(passport, "AGENT_OWNERSHIP")

    def test_writer_may_use_a_path_below_an_owned_root(self):
        passport = valid_passport(); passport["subgoals"][1]["ownedPaths"] = ["src"]; passport["agents"][0]["ownedPaths"] = ["src/x.py"]
        self.assertEqual([], validate_passport(passport))

    def test_chain_paths_must_be_normalized_and_stay_in_harness_roots(self):
        invalid = (
            ("canonicalWorkItemPath", "README.md"),
            ("canonicalWorkItemPath", r"C:\outside\goal.md"),
            ("canonicalWorkItemPath", r".harness/work\..\..\outside.md"),
            ("metricsPath", "../outside.jsonl"),
            ("metricsPath", r".harness\metrics\runs.jsonl"),
        )
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                passport = valid_passport(); passport["chain"][field] = value
                self.assert_code(passport, "PATH_SAFETY")

    def test_subgoal_and_agent_declarations_reject_path_escape(self):
        mutations = (
            lambda passport: passport["subgoals"][1].update({"worktree": "../outside"}),
            lambda passport: passport["subgoals"][1].update({"ownedPaths": ["../outside.py"]}),
            lambda passport: passport["agents"][0].update({"ownedPaths": ["src/../outside.py"]}),
            lambda passport: passport["agents"][0].update({"worktree": r"C:\outside"}),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                passport = valid_passport(); mutate(passport)
                self.assert_code(passport, "PATH_SAFETY")

    def test_complete_chain_rejects_unfinished_subgoals(self):
        passport = valid_passport(); passport["chain"]["status"] = "complete"; passport["agents"][0]["status"] = "done"
        self.assert_code(passport, "CHAIN_COMPLETE")

    def test_check_cli_prints_one_pass_line(self):
        passport_file = Path(__file__).parent / "fixtures" / "valid_goal_passport.json"
        result = subprocess.run([sys.executable, "goal_runner_validator.py", "check", str(passport_file)], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode)
        self.assertEqual("PASS goal passport is valid\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
