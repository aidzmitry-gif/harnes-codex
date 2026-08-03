import argparse
import unittest
from unittest.mock import patch

import acceptance_gate


class AcceptanceGateTests(unittest.TestCase):
    def command(self, command, **extra):
        return {"id": "command", "kind": "command", "command": command, **extra}

    def test_legacy_gate_is_valid_and_save_upgrades_schema(self):
        data = {"criteria": [self.command("python -c \"pass\"")]}
        acceptance_gate.validate(data)
        with patch("pathlib.Path.mkdir"), patch("pathlib.Path.write_text") as write:
            acceptance_gate.save(acceptance_gate.root() / "gate.json", data)
        self.assertEqual(2, data["schemaVersion"])
        self.assertIn('"schemaVersion": 2', write.call_args.args[0])

    @patch("acceptance_gate.fingerprint")
    def test_manual_evidence_requires_matching_fingerprint(self, mocked_fingerprint):
        before = {"algorithm": "sha256", "value": "before", "status": "ok"}
        after = {"algorithm": "sha256", "value": "after", "status": "ok"}
        mocked_fingerprint.return_value = before
        criterion = {"id": "manual", "kind": "manual", "passes": True, "evidence": "reviewed"}
        criterion["fingerprint"] = acceptance_gate.fingerprint()
        self.assertTrue(acceptance_gate.evaluate(criterion)[0])
        mocked_fingerprint.return_value = after
        self.assertEqual((False, "stale manual evidence: re-prove required"), acceptance_gate.evaluate(criterion))

    def test_legacy_manual_evidence_requires_reprove(self):
        self.assertEqual((False, "stale manual evidence: re-prove required"), acceptance_gate.evaluate(
            {"id": "manual", "kind": "manual", "passes": True, "evidence": "old"}
        ))

    @patch("acceptance_gate.save")
    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    @patch("acceptance_gate.gate_path")
    def test_prove_records_fresh_manual_evidence(self, mocked_path, mocked_load, _, mocked_save):
        mocked_path.return_value = acceptance_gate.root() / "gate.json"
        data = {"criteria": [{"id": "manual", "kind": "manual", "passes": False, "evidence": ""}]}
        mocked_load.return_value = data
        with patch("pathlib.Path.exists", return_value=True):
            result = acceptance_gate.prove(argparse.Namespace(work_item="item", criterion="manual", evidence="reviewed"))
        criterion = data["criteria"][0]
        self.assertEqual(0, result)
        self.assertEqual("reviewed", criterion["evidence"])
        self.assertEqual(0, criterion["durationMs"])
        self.assertIn("checkedAt", criterion)
        self.assertEqual("fresh", criterion["fingerprint"]["value"])
        self.assertTrue(acceptance_gate.evaluate(criterion)[0])
        mocked_save.assert_called_once()

    def test_command_records_timestamp_duration_and_failure(self):
        criterion = self.command("python -c \"raise SystemExit(3)\"")
        passed, _ = acceptance_gate.evaluate(criterion)
        self.assertFalse(passed)
        self.assertIn("checkedAt", criterion)
        self.assertIsInstance(criterion["durationMs"], int)
        self.assertGreaterEqual(criterion["durationMs"], 0)
        self.assertIn("fingerprint", criterion)

    def test_command_timeout_is_recorded_failure(self):
        criterion = self.command("python -c \"import time; time.sleep(2)\"", timeoutSeconds=1)
        passed, evidence = acceptance_gate.evaluate(criterion)
        self.assertFalse(passed)
        self.assertIn("timeout", evidence)

    def test_timeout_must_be_in_bounds(self):
        with self.assertRaises(ValueError):
            acceptance_gate.validate({"criteria": [self.command("echo ok", timeoutSeconds=0)]})

    @patch("acceptance_gate.git_output")
    def test_git_fingerprint_never_reads_sensitive_or_evidence_paths(self, mocked_git):
        mocked_git.side_effect = ["true\n", "head\n", "safe.txt\0.env\0.harness/acceptance/a.json\0secrets/key\0", "", "new.txt\0.env.local\0"]
        with patch("acceptance_gate.digest_files", return_value="content"):
            acceptance_gate.fingerprint()
        diff_call = mocked_git.call_args_list[3].args
        self.assertEqual(("diff", "--binary", "HEAD", "--", "safe.txt"), diff_call)

    @patch("pathlib.Path.exists", return_value=True)
    @patch("acceptance_gate.git_output", side_effect=OSError)
    def test_unavailable_git_state_is_never_fabricated(self, _, __):
        self.assertEqual("unavailable", acceptance_gate.fingerprint()["status"])


if __name__ == "__main__":
    unittest.main()
