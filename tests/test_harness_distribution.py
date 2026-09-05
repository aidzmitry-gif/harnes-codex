import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

import harness_distribution as hd


class HarnessDistributionTests(unittest.TestCase):
    def setUp(self):
        # Workspace fixtures avoid host TEMP ACLs; cleanup is bounded to this UUID.
        test_root = Path(__file__).resolve().parents[1] / ".harness" / "test-tmp"
        self.base = test_root / ("distribution-" + uuid.uuid4().hex)
        self.base.mkdir(parents=True)
        self.assertEqual(self.base.resolve().parent, test_root.resolve())
        self.addCleanup(shutil.rmtree, self.base, onerror=self.remove_owned_readonly)
        self.source = self.base / "source"
        self.project = self.base / "project"
        self.source.mkdir()
        self.project.mkdir()
        for name in hd.FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{}\n" if name.endswith(".json") else b"# fixture\n")
        self.publish("test-1")

    def remove_owned_readonly(self, function, path, error):
        target = Path(path)
        # Git objects on Windows have the read-only attribute, not a denied ACL.
        # Do not change permissions on any other file or escape this UUID fixture.
        self.assertIn(self.base.resolve(), target.resolve().parents)
        if os.name != "nt" or not (target.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY):
            raise error[1]
        os.chmod(target, stat.S_IWRITE)
        function(path)

    def publish(self, version):
        manifest = hd.release_manifest(self.source, version)
        (self.source / hd.RELEASE).write_bytes(hd.encoded(manifest))
        return manifest

    def install(self):
        plan = hd.inspect(self.source, self.project)[0]
        return hd.apply(self.source, self.project, plan["planHash"], idle_confirmed=True)

    def test_real_repository_bundle_parses_without_running_project_commands(self):
        source = Path(__file__).resolve().parents[1]
        manifest = hd.release_manifest(source, "integration-test")
        self.assertEqual(set(manifest["files"]), set(hd.FILES))
        for name in hd.FILES:
            if name.endswith(".py"):
                hd.ast.parse((source / name).read_bytes())

    @unittest.skipUnless(shutil.which("git"), "Git not available")
    def test_manifest_survives_git_checkout_with_windows_autocrlf(self):
        repo = Path(__file__).resolve().parents[1]
        shutil.copyfile(repo / ".gitattributes", self.source / ".gitattributes")
        exported = self.base / "checkout"
        exported.mkdir()
        for arguments in (("init", "--quiet"), ("add", "--all"),
                          ("checkout-index", "--all", "--prefix=" + exported.as_posix() + "/")):
            result = subprocess.run(["git", "-C", str(self.source), "-c", "core.autocrlf=true", *arguments],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(hd.load_release(exported)[0], hd.load_release(self.source)[0])

    def test_plan_is_read_only_and_first_install_verifies_repeat_is_noop(self):
        before = list(self.project.rglob("*"))
        plan = hd.inspect(self.source, self.project)[0]
        self.assertTrue(plan["canApply"])
        self.assertEqual(before, list(self.project.rglob("*")))
        result = self.install()
        self.assertEqual(result["verifiedFiles"], len(hd.FILES))
        self.assertFalse(result["profileConfigured"])
        self.assertEqual(result["projectAcceptance"], "not-run")
        files = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertFalse(self.install()["changed"])
        self.assertEqual(files, {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob("*") if p.is_file()})

    def test_protected_project_data_remains_byte_identical(self):
        protected = ("AGENTS.md", "CLAUDE.md", "harness.config.json", ".env", ".harness/CONTEXT.md",
                     ".harness/work/current.md", ".harness/runtime/update-radar-state.json")
        for name in protected:
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"owner-specific data\x00\r\n")
        self.assertTrue(self.install()["profileConfigured"])
        for name in protected:
            self.assertEqual((self.project / name).read_bytes(), b"owner-specific data\x00\r\n")

    def test_unmanaged_conflict_blocks_whole_install_before_writes(self):
        (self.project / "acceptance_gate.py").write_text("# owner version\n")
        plan = hd.inspect(self.source, self.project)[0]
        self.assertFalse(plan["canApply"])
        with self.assertRaises(hd.DistributionError):
            hd.apply(self.source, self.project, plan["planHash"], idle_confirmed=True)
        self.assertEqual([p.name for p in self.project.iterdir()], ["acceptance_gate.py"])

    def test_exact_existing_content_can_be_adopted_but_never_overwritten_blindly(self):
        (self.project / "acceptance_gate.py").write_bytes((self.source / "acceptance_gate.py").read_bytes())
        self.assertTrue(self.install()["changed"])
        self.assertEqual(hd.verify(self.project)["status"], "verified")

    def test_update_uses_prior_hash_and_keeps_backup(self):
        self.install()
        old = (self.project / "goal_orchestrator.py").read_bytes()
        (self.source / "goal_orchestrator.py").write_bytes(b"# new release\n")
        self.publish("test-2")
        result = self.install()
        self.assertEqual(result["releaseId"], "test-2")
        self.assertEqual((Path(result["backup"]) / "goal_orchestrator.py").read_bytes(), old)

    def test_modified_or_missing_managed_file_is_conflict_even_if_new_release_matches(self):
        for replacement in (b"# changed\n", None):
            with self.subTest(replacement=replacement):
                path = self.project / "goal_orchestrator.py"
                if (self.project / hd.RECEIPT).exists():
                    path.write_bytes((self.source / "goal_orchestrator.py").read_bytes())
                else:
                    self.install()
                if replacement is None:
                    path.unlink()
                else:
                    path.write_bytes(replacement)
                self.assertFalse(hd.inspect(self.source, self.project)[0]["canApply"])

    def test_stale_plan_and_missing_idle_acknowledgement_fail_closed(self):
        plan = hd.inspect(self.source, self.project)[0]
        with self.assertRaises(hd.DistributionError):
            hd.apply(self.source, self.project, plan["planHash"])
        (self.project / "goal_progress.py").write_bytes(b"# foreign\n")
        with self.assertRaises(hd.DistributionError):
            hd.apply(self.source, self.project, plan["planHash"], idle_confirmed=True)
        self.assertFalse((self.project / ".harness").exists())

    def test_release_tamper_duplicate_keys_and_path_escape_are_rejected(self):
        manifest = self.publish("test-1")
        (self.source / "goal_progress.py").write_bytes(b"# tamper\n")
        with self.assertRaises(hd.DistributionError):
            hd.inspect(self.source, self.project)
        manifest["files"]["../AGENTS.md"] = "0" * 64
        with self.assertRaises(hd.DistributionError):
            hd.validate_manifest(manifest)
        with self.assertRaises(hd.DistributionError):
            hd.parse(b'{"schemaVersion":1,"schemaVersion":1}')

    def test_manifest_rejects_invalid_schema_and_hash(self):
        for key, value in (("schemaVersion", True), ("schemaVersion", 2), ("bundleHash", "0" * 64), ("releaseId", "../bad")):
            manifest = self.publish("test-1")
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(hd.DistributionError):
                hd.validate_manifest(manifest)

    def test_stale_lock_is_not_cleared(self):
        lock = self.project / hd.LOCK
        lock.mkdir(parents=True)
        with self.assertRaises(hd.DistributionError):
            hd.inspect(self.source, self.project)
        self.assertTrue(lock.is_dir())

    def test_mid_transaction_failure_rolls_back_updated_and_new_files(self):
        self.install()
        (self.source / "acceptance_gate.py").write_bytes(b"# updated\n")
        (self.source / "goal_runner_validator.py").write_bytes(b"# updated\n")
        self.publish("test-2")
        original = hd.snapshot(self.project)
        writer = hd.atomic_write
        calls = 0

        def fail_second(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            return writer(path, content)

        with patch.object(hd, "atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(hd.snapshot(self.project), original)
        self.assertFalse((self.project / hd.LOCK).exists())

    def test_first_install_failure_removes_only_new_managed_files(self):
        writer = hd.atomic_write
        calls = 0

        def fail_second(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            return writer(path, content)

        with patch.object(hd, "atomic_write", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.install()
        self.assertTrue(all(value is None for value in hd.snapshot(self.project).values()))

    def test_concurrent_foreign_edit_is_retained_and_lock_blocks_retry(self):
        writer = hd.atomic_write
        calls = 0

        def edit_then_fail(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.project / "acceptance_gate.py").write_bytes(b"# concurrent owner\n")
                raise OSError("injected external edit")
            return writer(path, content)

        with patch.object(hd, "atomic_write", side_effect=edit_then_fail):
            with self.assertRaisesRegex(hd.DistributionError, "rollback incomplete"):
                self.install()
        self.assertEqual((self.project / "acceptance_gate.py").read_bytes(), b"# concurrent owner\n")
        self.assertTrue((self.project / hd.LOCK).is_dir())

    def test_relative_nested_roots_and_reparse_paths_are_rejected(self):
        with self.assertRaises(hd.DistributionError):
            hd.checked_root(Path("//server/share/project"))
        with self.assertRaises(hd.DistributionError):
            hd.checked_root(Path("relative"))
        with self.assertRaises(hd.DistributionError):
            hd.inspect(self.source, self.source)
        nested = self.source / "nested"
        nested.mkdir()
        with self.assertRaises(hd.DistributionError):
            hd.inspect(self.source, nested)
        original = hd.is_link
        with patch.object(hd, "is_link", side_effect=lambda p: p == self.project or original(p)):
            with self.assertRaises(hd.DistributionError):
                hd.inspect(self.source, self.project)

    def test_cli_manifest_plan_apply_verify_and_invalid_input(self):
        arguments = ["--source", str(self.source), "--project", str(self.project)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(hd.main(["plan", *arguments]), 0)
        plan = json.loads(out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hd.main(["apply", *arguments, "--plan-hash", plan["planHash"], "--idle-confirmed"]), 0)
            self.assertEqual(hd.main(["verify", "--project", str(self.project)]), 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(hd.main(["plan", "--source", "relative", "--project", str(self.project)]), 2)

    def registry(self, entries=None):
        return {"schemaVersion": 1, "projects": entries or [
            {"name": "Проверка UTF-8", "path": str(self.project), "hostId": "local"}]}

    def test_registry_rejects_ambiguous_schema_and_overlapping_roots(self):
        path = self.base / "registry.json"
        bad_values = []
        for changes in ({"deferedReason": "do not apply"}, {"hostId": "remote"},
                        {"deferredReason": ""}, {"path": "relative"}, {"name": True}):
            value = self.registry()
            value["projects"][0].update(changes)
            bad_values.append(value)
        bad_values.extend(({"schemaVersion": True, "projects": self.registry()["projects"]},
                           {"schemaVersion": 1, "projects": []}, {"schemaVersion": 1, "projects": {}}))
        same = self.registry()["projects"][0]
        bad_values.append(self.registry([same, same.copy()]))
        child = {**same, "path": str(self.project / "child")}
        bad_values.append(self.registry([same, child]))
        for value in bad_values:
            with self.subTest(value=value):
                path.write_bytes(hd.encoded(value))
                with self.assertRaises(hd.DistributionError):
                    hd.load_registry(path)
        path.write_bytes(hd.encoded(self.registry([same, {**child, "deferredReason": "nested"}])))
        self.assertEqual(len(hd.load_registry(path)["projects"]), 2)

    @unittest.skipUnless(shutil.which("powershell") or shutil.which("pwsh"), "PowerShell not available")
    def test_wrapper_rejects_entire_bad_registry_and_reports_verified_outcomes(self):
        repo = Path(__file__).resolve().parents[1]
        wrapper = self.source / "scripts/Update-HarnessProjects.ps1"
        shutil.copyfile(repo / "scripts/Update-HarnessProjects.ps1", wrapper)
        shutil.copyfile(repo / "harness_distribution.py", self.source / "harness_distribution.py")
        path = self.base / "registry.json"

        def run(*arguments):
            return subprocess.run([shutil.which("powershell") or shutil.which("pwsh"), "-NoProfile",
                                   "-File", str(wrapper), "-RegistryPath", str(path),
                                   "-PythonExecutable", sys.executable, *arguments],
                                  capture_output=True, encoding="utf-8", errors="replace", timeout=30)

        duplicate = hd.encoded(self.registry()).replace(b'"schemaVersion": 1', b'"schemaVersion": 1, "schemaVersion": 1')
        typo = self.registry()
        typo["projects"].append({"name": "typo", "path": str(self.base / "other"), "hostId": "local", "deferedReason": "stop"})
        for content in (duplicate, hd.encoded(typo)):
            path.write_bytes(content)
            result = run("-Apply", "-IdleConfirmed")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse((self.project / hd.RECEIPT).exists())
        path.write_bytes(hd.encoded(self.registry()))
        preview = run()
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(json.loads(preview.stdout)["status"], "planned")
        self.assertFalse((self.project / hd.RECEIPT).exists())
        self.assertNotEqual(run("-Apply").returncode, 0)
        self.assertEqual(run("-Apply", "-IdleConfirmed", "-WhatIf").returncode, 0)
        self.assertFalse((self.project / hd.RECEIPT).exists())
        for status in ("installed", "current"):
            result = run("-Apply", "-IdleConfirmed")
            self.assertEqual(result.returncode, 0, result.stderr)
            row = json.loads(result.stdout)
            self.assertEqual(row["status"], status)
            self.assertEqual(row["project"], "Проверка UTF-8")
            self.assertEqual(row["evidence"]["verifiedFiles"], 18)
            self.assertEqual(row["evidence"]["projectAcceptance"], "not-run")
        (self.project / "goal_progress.py").write_bytes(b"# owner edit\n")
        entries = self.registry()["projects"] + [
            {"name": "absent", "path": str(self.base / "absent"), "hostId": "local"},
            {"name": "busy", "path": str(self.base / "busy"), "hostId": "local", "deferredReason": "active task"}]
        path.write_bytes(hd.encoded(self.registry(entries)))
        result = run("-Apply", "-IdleConfirmed")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual([json.loads(line)["status"] for line in result.stdout.splitlines()],
                         ["conflict", "unavailable", "deferred"])


if __name__ == "__main__":
    unittest.main()
