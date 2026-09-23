import argparse
import contextlib
import io
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
        criterion["definitionDigest"] = acceptance_gate.criterion_definition_digest(criterion)
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
        criterion = self.command("raise-error", id="check", passes=True, evidence="saved", fingerprint=acceptance_gate.fingerprint())
        criterion["definitionDigest"] = acceptance_gate.command_definition_digest(criterion)
        mocked_load.return_value = {"criteria": [criterion]}
        self.assertEqual((True, "fresh stored acceptance evidence"), acceptance_gate.stored_evidence_is_fresh("item", "check"))
        run.assert_not_called()

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    def test_stored_command_evidence_rejects_changed_definition(self, mocked_load, _):
        criterion = self.command("new-command", id="check", passes=True, evidence="saved", fingerprint=acceptance_gate.fingerprint())
        criterion["definitionDigest"] = acceptance_gate.command_definition_digest(self.command("old-command"))
        mocked_load.return_value = {"criteria": [criterion]}
        self.assertEqual(
            (False, "stale command definition: reverify required"),
            acceptance_gate.stored_evidence_is_fresh("item", "check"),
        )

    def test_definition_digest_binds_every_command_oracle_field(self):
        criterion = self.command("python check.py", description="Run check", timeoutSeconds=20, cwd="tests", expect="PASS CHECK")
        baseline = acceptance_gate.command_definition_digest(criterion)
        for field, value in (("id", "other"), ("kind", "manual"), ("description", "Different check"),
                             ("command", "python other.py"), ("timeoutSeconds", 21),
                             ("cwd", "scripts"), ("expect", "FAIL")):
            with self.subTest(field=field):
                self.assertNotEqual(baseline, acceptance_gate.command_definition_digest({**criterion, field: value}))

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    def test_manual_definition_and_kind_changes_revoke_stored_evidence(self, mocked_load, _):
        current = acceptance_gate.fingerprint()
        manual = {"id": "review", "kind": "manual", "description": "Review implementation",
                  "passes": True, "evidence": "Reviewed", "fingerprint": current}
        manual["definitionDigest"] = acceptance_gate.criterion_definition_digest(manual)
        mocked_load.return_value = {"criteria": [manual]}
        self.assertTrue(acceptance_gate.stored_evidence_is_fresh("item", "review")[0])
        manual["description"] = "Approve release"
        self.assertEqual((False, "stale manual definition: re-prove required"),
                         acceptance_gate.stored_evidence_is_fresh("item", "review"))
        self.assertFalse(acceptance_gate.evaluate(manual)[0])
        manual.pop("definitionDigest")
        self.assertFalse(acceptance_gate.stored_evidence_is_fresh("item", "review")[0])

        command = self.command("python check.py", id="check", passes=True, evidence="auto: exit 0", fingerprint=current)
        command["definitionDigest"] = acceptance_gate.command_definition_digest(command)
        command["kind"] = "manual"
        mocked_load.return_value = {"criteria": [command]}
        self.assertFalse(acceptance_gate.stored_evidence_is_fresh("item", "check")[0])

    def test_cwd_and_expect_are_validated(self):
        for cwd in ("", "../outside", "tests/../../outside", "C:/outside", "tests\\nested", "/outside"):
            with self.subTest(cwd=cwd), self.assertRaises(ValueError):
                acceptance_gate.validate({"criteria": [self.command("echo ok", cwd=cwd)]})
        for expect in ("", " \t", "x" * 1025):
            with self.subTest(expect=expect[:12]), self.assertRaises(ValueError):
                acceptance_gate.validate({"criteria": [self.command("echo ok", expect=expect)]})

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.subprocess.run")
    def test_command_requires_zero_exit_and_expected_marker(self, run, _):
        run.return_value = type("Result", (), {"returncode": 0, "stdout": "finished", "stderr": ""})()
        criterion = self.command("python check.py", expect="PASS CHECK")
        passed, evidence = acceptance_gate.evaluate(criterion)
        self.assertFalse(passed)
        self.assertIn("expected marker missing", evidence)
        self.assertEqual(acceptance_gate.command_definition_digest(criterion), criterion["definitionDigest"])

        run.return_value = type("Result", (), {"returncode": 0, "stdout": "PASS CHECK", "stderr": ""})()
        passed, evidence = acceptance_gate.evaluate(criterion)
        self.assertTrue(passed)
        self.assertIn("expected marker matched", evidence)

        run.return_value = type("Result", (), {"returncode": 1, "stdout": "PASS CHECK", "stderr": ""})()
        passed, _ = acceptance_gate.evaluate(criterion)
        self.assertFalse(passed)

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "", "status": "unavailable"})
    @patch("acceptance_gate.subprocess.run")
    def test_unavailable_fingerprint_cannot_report_command_pass(self, run, _):
        passed, evidence = acceptance_gate.evaluate(self.command("python check.py"))
        self.assertFalse(passed)
        self.assertIn("fingerprint unavailable", evidence)
        run.assert_not_called()

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.subprocess.run")
    def test_command_uses_declared_repository_cwd(self, run, _):
        run.return_value = type("Result", (), {"returncode": 0, "stdout": "OK", "stderr": ""})()
        passed, _ = acceptance_gate.evaluate(self.command("python check.py", cwd="tests", expect="OK"))
        self.assertTrue(passed)
        self.assertEqual((acceptance_gate.root() / "tests").resolve(), run.call_args.kwargs["cwd"])

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.subprocess.run", side_effect=AssertionError("status must not execute checks"))
    def test_status_is_read_only_and_detects_changed_definition(self, run, _):
        criterion = self.command("old-command", id="check", passes=True, evidence="saved success", fingerprint=acceptance_gate.fingerprint())
        criterion["definitionDigest"] = acceptance_gate.command_definition_digest(criterion)
        data = {"criteria": [criterion]}
        target = acceptance_gate.root() / ".harness" / "acceptance" / "item.json"
        with patch("acceptance_gate.gate_path", return_value=target), patch("acceptance_gate.load", return_value=data), \
                patch("pathlib.Path.exists", return_value=True), patch("acceptance_gate.save") as save, \
                patch("pathlib.Path.write_text") as write_text:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = acceptance_gate.status(argparse.Namespace(work_item="item"))
            self.assertEqual(0, result)
            self.assertIn("PASS check: fresh stored acceptance evidence", output.getvalue())

            criterion["command"] = "new-command"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = acceptance_gate.status(argparse.Namespace(work_item="item"))
            self.assertEqual(2, result)
            self.assertIn("stale command definition", output.getvalue())
        save.assert_not_called()
        write_text.assert_not_called()
        run.assert_not_called()

    def test_reverify_cli_routes_to_full_check(self):
        with patch("sys.argv", ["acceptance_gate.py", "reverify", "item"]), patch("acceptance_gate.check", return_value=0) as check:
            self.assertEqual(0, acceptance_gate.main())
            check.assert_called_once()

    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "fresh", "status": "ok"})
    @patch("acceptance_gate.load")
    def test_stored_evidence_missing_or_stale_fails_closed(self, mocked_load, _):
        criterion = {"id": "check", "kind": "manual", "passes": True, "evidence": "", "fingerprint": acceptance_gate.fingerprint()}
        criterion["definitionDigest"] = acceptance_gate.criterion_definition_digest(criterion)
        mocked_load.return_value = {"criteria": [criterion]}
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
        self.assertEqual(acceptance_gate.criterion_definition_digest(criterion), criterion["definitionDigest"])
        self.assertTrue(acceptance_gate.evaluate(criterion)[0])
        mocked_save.assert_called_once()

    @patch("acceptance_gate.save")
    @patch("acceptance_gate.fingerprint", return_value={"algorithm": "sha256", "value": "", "status": "unavailable"})
    @patch("acceptance_gate.load")
    @patch("acceptance_gate.gate_path")
    def test_prove_rejects_unavailable_fingerprint_without_write(self, mocked_path, mocked_load, _, mocked_save):
        mocked_path.return_value = acceptance_gate.root() / "gate.json"
        mocked_load.return_value = {"criteria": [{"id": "review", "kind": "manual", "passes": False, "evidence": ""}]}
        with patch("pathlib.Path.exists", return_value=True):
            result = acceptance_gate.prove(argparse.Namespace(work_item="item", criterion="review", evidence="reviewed"))
        self.assertEqual(2, result)
        self.assertFalse(mocked_load.return_value["criteria"][0]["passes"])
        mocked_save.assert_not_called()

    def test_command_records_timestamp_duration_and_failure(self):
        criterion = self.command("python -c \"raise SystemExit(3)\"")
        passed, _ = acceptance_gate.evaluate(criterion)
        self.assertFalse(passed)
        self.assertIn("checkedAt", criterion)
        self.assertIsInstance(criterion["durationMs"], int)
        self.assertGreaterEqual(criterion["durationMs"], 0)
        self.assertIn("fingerprint", criterion)
        self.assertEqual(acceptance_gate.command_definition_digest(criterion), criterion["definitionDigest"])

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
