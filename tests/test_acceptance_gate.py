import argparse
import unittest
from pathlib import PurePosixPath
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

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    @patch("acceptance_gate.subprocess.run")
    def test_stored_command_evidence_is_read_without_execution(self, run, mocked_load, _):
        mocked_load.return_value = {"criteria": [{"id": "check", "kind": "command", "command": "raise-error", "passes": True, "evidence": "saved", "fingerprint": acceptance_gate.fingerprint()}]}
        self.assertEqual((True, "fresh stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))
        run.assert_not_called()

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    def test_stored_evidence_missing_or_stale_fails_closed(self, mocked_load, _):
        mocked_load.return_value = {"criteria": [{"id": "check", "kind": "manual", "passes": True, "evidence": "", "fingerprint": acceptance_gate.fingerprint()}]}
        self.assertEqual((False, "missing stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))
        mocked_load.return_value["criteria"][0].update({"evidence": "saved", "fingerprint": {"algorithm": "sha256", "value": "old", "status": "ok"}})
        self.assertEqual((False, "stale stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    def test_non_boolean_passes_never_opens_stored_evidence(self, mocked_load, _):
        criterion = {"id": "check", "kind": "manual", "passes": "false", "evidence": "saved", "fingerprint": acceptance_gate.fingerprint()}
        mocked_load.return_value = {"criteria": [criterion]}
        self.assertEqual((False, "missing stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))
        criterion["passes"] = 1
        self.assertEqual((False, "missing stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))
        self.assertFalse(acceptance_gate.evaluate(criterion)[0])

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

    def test_empty_command_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty command"):
            acceptance_gate.validate({"criteria": [self.command("   ")]})

    def test_sensitive_paths_are_excluded_but_passports_are_relevant(self):
        for name in (".env.local", "secrets/key", "credentials.json", ".ssh/id_rsa", "config/private.pem"):
            self.assertTrue(acceptance_gate.excluded(PurePosixPath(name)), name)
        self.assertTrue(acceptance_gate.excluded(PurePosixPath(".harness/work/notes.md")))
        self.assertFalse(acceptance_gate.excluded(PurePosixPath(".harness/work/goal.passport.json")))
        self.assertFalse(acceptance_gate.excluded(PurePosixPath("src/credential_validator.py")))

    def test_explicit_ignored_path_is_safe_and_narrow(self):
        ignored = acceptance_gate.normalize_ignored_paths({".harness/work/goal.passport.json"})
        self.assertTrue(acceptance_gate.excluded(PurePosixPath(".harness/work/goal.passport.json"), ignored))
        self.assertFalse(acceptance_gate.excluded(PurePosixPath(".harness/work/other.passport.json"), ignored))
        with self.assertRaises(ValueError):
            acceptance_gate.normalize_ignored_paths({"../outside"})

    def test_sensitive_files_are_never_read_for_fingerprinting(self):
        sensitive = [".env.local", "secrets/key", "credentials.json", ".ssh/id_rsa", "config/private.pem"]
        with patch("pathlib.Path.read_bytes", side_effect=AssertionError("sensitive file read")) as read_bytes:
            acceptance_gate.digest_files(acceptance_gate.root(), sensitive)
        read_bytes.assert_not_called()

    @patch("acceptance_gate.git_output")
    def test_fingerprint_ignores_evidence_only_commits_but_tracks_passport(self, mocked_git):
        stable = "100644 aaa 0\tsafe.txt\0"
        excluded_before = stable + "100644 old 0\t.harness/acceptance/a.json\0"
        excluded_after = stable + "100644 new 0\t.harness/acceptance/a.json\0"
        passport_after = stable + "100644 plan 0\t.harness/work/goal.passport.json\0"
        mocked_git.side_effect = [
            "true\n", excluded_before, "", "",
            "true\n", excluded_after, "", "",
            "true\n", passport_after, "", "",
        ]
        before = acceptance_gate.fingerprint()
        self.assertEqual(before, acceptance_gate.fingerprint())
        self.assertNotEqual(before, acceptance_gate.fingerprint())

    @patch("pathlib.Path.exists", return_value=True)
    @patch("acceptance_gate.git_output", side_effect=OSError)
    def test_unavailable_git_state_is_never_fabricated(self, _, __):
        self.assertEqual("unavailable", acceptance_gate.fingerprint()["status"])


if __name__ == "__main__":
    unittest.main()
