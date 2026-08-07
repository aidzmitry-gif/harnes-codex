import json
import unittest
from unittest.mock import patch

import goal_progress
from goal_runner_validator import validate_passport
from tests.test_goal_runner_validator import valid_passport


FINGERPRINT = {"algorithm": "sha256", "status": "ok", "value": "a" * 64}


class GoalProgressTests(unittest.TestCase):
    def invoke(self, action="check", strategy="minimal"):
        return goal_progress.main([action, "passport.json", "G02", strategy])

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    def test_first_attempt_checks_then_records_and_passport_stays_valid(self, _, read_text, save_atomic):
        read_text.return_value = json.dumps(valid_passport())
        self.assertEqual(0, self.invoke())
        self.assertEqual(0, self.invoke("record"))
        stored = save_atomic.call_args.args[1]
        self.assertEqual([], validate_passport(stored))
        self.assertEqual(1, len(stored["goalProgress"]["attempts"]))

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    def test_exact_repeat_is_no_progress_and_check_is_read_only(self, _, read_text, save_atomic):
        passport = valid_passport()
        read_text.return_value = json.dumps(passport)
        self.assertEqual(0, self.invoke("record"))
        recorded = save_atomic.call_args.args[1]
        read_text.return_value = json.dumps(recorded)
        save_atomic.reset_mock()
        self.assertEqual(1, self.invoke())
        save_atomic.assert_not_called()

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    def test_changed_strategy_is_new_attempt(self, _, read_text, save_atomic):
        read_text.return_value = json.dumps(valid_passport())
        self.assertEqual(0, self.invoke("record"))
        read_text.return_value = json.dumps(save_atomic.call_args.args[1])
        self.assertEqual(0, self.invoke(strategy="alternate"))

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text", return_value=json.dumps(valid_passport()))
    @patch("goal_progress.acceptance_gate.fingerprint")
    def test_changed_repository_fingerprint_is_new_attempt(self, mocked_fingerprint, read_text, save_atomic):
        mocked_fingerprint.return_value = FINGERPRINT
        self.assertEqual(0, self.invoke("record"))
        read_text.return_value = json.dumps(save_atomic.call_args.args[1])
        self.assertEqual(1, self.invoke())
        mocked_fingerprint.return_value = {**FINGERPRINT, "value": "b" * 64}
        self.assertEqual(0, self.invoke())

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.stored_evidence_is_fresh", return_value=(True, "fresh"))
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    @patch("goal_progress.acceptance_gate.load")
    def test_evidence_text_does_not_change_attempt_signature(self, mocked_load, _, __, read_text, save_atomic):
        passport = valid_passport(); passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        read_text.return_value = json.dumps(passport)
        criterion = {"id": "acceptance", "kind": "manual", "passes": True, "evidence": "first", "fingerprint": FINGERPRINT}
        mocked_load.return_value = {"criteria": [criterion]}
        self.assertEqual(0, self.invoke("record"))
        read_text.return_value = json.dumps(save_atomic.call_args.args[1])
        criterion["evidence"] = "changed"
        self.assertEqual(1, self.invoke())

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.stored_evidence_is_fresh", return_value=(True, "fresh"))
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    @patch("goal_progress.acceptance_gate.load")
    def test_changed_structured_evidence_state_is_new_attempt(self, mocked_load, _, __, read_text, save_atomic):
        passport = valid_passport(); passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        read_text.return_value = json.dumps(passport)
        criterion = {"id": "acceptance", "kind": "manual", "passes": False, "evidence": "saved", "fingerprint": FINGERPRINT}
        mocked_load.return_value = {"criteria": [criterion]}
        self.assertEqual(0, self.invoke("record"))
        read_text.return_value = json.dumps(save_atomic.call_args.args[1])
        criterion["passes"] = True
        self.assertEqual(0, self.invoke())

    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    def test_malformed_state_fails_closed(self, _, read_text):
        passport = valid_passport(); passport["goalProgress"] = {"schemaVersion": 1, "attempts": [{"chainId": "HRE-001"}]}
        read_text.return_value = json.dumps(passport)
        self.assertEqual(2, self.invoke())

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    def test_invalid_passport_is_not_recorded(self, read_text, save_atomic):
        passport = valid_passport(); passport["chain"]["riskClass"] = "invalid"
        read_text.return_value = json.dumps(passport)
        self.assertEqual(2, self.invoke("record"))
        save_atomic.assert_not_called()

    @patch("goal_progress.save_atomic")
    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    def test_attempt_limit_fails_closed(self, _, read_text, save_atomic):
        passport = valid_passport()
        passport["goalProgress"] = {
            "schemaVersion": 1,
            "attempts": [
                {
                    "chainId": "HRE-001",
                    "subgoalId": "G02",
                    "strategyId": f"s{index}",
                    "repositoryFingerprint": FINGERPRINT,
                    "unlockEvidenceFingerprint": None,
                }
                for index in range(goal_progress.MAX_ATTEMPTS + 1)
            ],
        }
        read_text.return_value = json.dumps(passport)
        self.assertEqual(2, self.invoke("record"))
        save_atomic.assert_not_called()

    @patch("goal_progress.Path.read_text")
    @patch("goal_progress.acceptance_gate.subprocess.run")
    @patch("goal_progress.acceptance_gate.stored_evidence_is_fresh", return_value=(True, "fresh"))
    @patch("goal_progress.acceptance_gate.fingerprint", return_value=FINGERPRINT)
    @patch("goal_progress.acceptance_gate.load")
    def test_referenced_command_evidence_never_executes_command(self, mocked_load, _, __, run, read_text):
        passport = valid_passport(); passport["subgoals"][1]["unlockEvidence"] = {"workItem": "hre-002", "criterionId": "acceptance"}
        read_text.return_value = json.dumps(passport)
        mocked_load.return_value = {"criteria": [{"id": "acceptance", "kind": "command", "command": "raise-error", "passes": True, "evidence": "saved", "fingerprint": FINGERPRINT}]}
        self.assertEqual(0, self.invoke())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
