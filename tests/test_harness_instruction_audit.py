import json
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import harness_instruction_audit as audit


def manifest(changes):
    paths = []
    for item in changes:
        if item["status"] == "renamed":
            paths.extend((item["from"], item["to"]))
        else:
            paths.append(item["path"])
    return {"schemaVersion": 1, "allowedPaths": paths, "changes": changes}


class HarnessInstructionAuditTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("repo")
        self.contents = {}
        self.reads = []
        self.exists = set()
        self.regular = set()

        def relative(path):
            return path.relative_to(self.root).as_posix()

        self.relative = relative
        self.patches = [
            patch.object(audit, "_checked_path", side_effect=lambda root, name: root / name),
            patch.object(audit, "_path_exists", side_effect=lambda path: relative(path) in self.exists),
            patch.object(audit, "_path_is_file", side_effect=lambda path: relative(path) in self.regular),
            patch.object(audit, "_path_size", side_effect=lambda path: len(self.contents[relative(path)])),
            patch.object(audit, "_read_path", side_effect=self._read),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def _read(self, path):
        name = self.relative(path)
        self.reads.append(name)
        return self.contents[name]

    def add_file(self, name, content):
        self.contents[name] = content.encode("utf-8")
        self.exists.add(name)
        self.regular.add(name)

    def test_changed_only_statuses_and_rename_are_explicit(self):
        self.add_file("new.md", "new body\n")
        self.add_file("same.md", "unchanged body\n")
        self.add_file("new-name.md", "renamed body\n")
        changes = [
            {"status": "modified", "path": "new.md"},
            {"status": "unchanged", "path": "same.md"},
            {"status": "deleted", "path": "gone.md"},
            {"status": "renamed", "from": "old-name.md", "to": "new-name.md"},
        ]
        result = audit.audit_manifest(self.root, manifest(changes))
        kinds = [item["kind"] for item in result["findings"]]
        self.assertIn("unchanged-skipped", kinds)
        self.assertIn("deleted-not-read", kinds)
        self.assertIn("renamed-path", kinds)
        self.assertEqual(self.reads, ["new.md", "new-name.md"])
        self.assertEqual(result["coverage"]["auditedChangedFiles"], 2)
        by_status = {item["status"]: item for item in result["coverage"]["fileCoverage"]}
        self.assertFalse(by_status["unchanged"]["contentRead"])
        self.assertFalse(by_status["deleted"]["contentRead"])
        self.assertFalse(by_status["renamed"]["oldContentRead"])
        self.assertTrue(by_status["renamed"]["newContentRead"])
        self.assertTrue(by_status["modified"]["contentRead"])

    def test_links_are_checked_without_fetching_or_reading_targets(self):
        tick = chr(96)
        self.add_file(
            "docs/changed.md",
            "[broken](missing.md) [inside](../shared.md) [web](https://example.test/x)\n"
            "[escape](../../outside.md) [secret](../.env)\n"
            "[credentials](../credentials.md) [secrets](../secrets.JSON)\n"
            + tick + "[code](not-a-link.md)" + tick + "\n"
            + tick * 3 + "md\n[code fence](not-a-link.md)\n"
            + tick * 3 + "\n",
        )
        self.add_file("shared.md", "target\n")
        self.exists.add("shared.md")
        result = audit.audit_manifest(
            self.root,
            manifest([{"status": "modified", "path": "docs/changed.md"}]),
        )
        findings = result["findings"]
        self.assertEqual([item["kind"] for item in findings].count("broken-local-link"), 1)
        self.assertEqual([item["kind"] for item in findings].count("unsafe-link-refused"), 4)
        self.assertEqual(self.reads, ["docs/changed.md"])
        self.assertEqual(result["coverage"]["externalLinksFetched"], 0)
        self.assertIn("reference-style links", result["coverage"]["notParsed"])
        self.assertNotIn(".env", json.dumps(result))

    def test_duplicate_candidates_are_exact_normalized_lines_without_content_dump(self):
        self.add_file("a.md", "Same   candidate\nunique a\n")
        self.add_file("b.md", " same candidate \nunique b\n")
        result = audit.audit_manifest(
            self.root,
            manifest([
                {"status": "modified", "path": "a.md"},
                {"status": "modified", "path": "b.md"},
            ]),
        )
        candidates = [item for item in result["findings"] if item["kind"] == "duplicate-candidate"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["occurrenceCount"], 2)
        self.assertEqual(len(candidates[0]["locations"]), 2)
        self.assertNotIn("same candidate", json.dumps(result))

    def test_unsafe_or_unlisted_paths_refuse_before_any_content_read(self):
        for unsafe in (
            "../outside.md", "C:/private.md", "/absolute.md", "//server/share.md",
            r"\\?\C:\secret.md", "docs/CON.md", ".env", "secrets/policy.md",
            "credentials.md", "secrets.md", "credentials.json", "ACCESS_TOKENS.MD",
        ):
            with self.subTest(path=unsafe):
                before = list(self.reads)
                with self.assertRaises(audit.AuditError):
                    audit.audit_manifest(
                        self.root,
                        manifest([{"status": "modified", "path": unsafe}]),
                    )
                self.assertEqual(self.reads, before)

        invalid = {
            "schemaVersion": 1,
            "allowedPaths": ["safe.md", "extra.md"],
            "changes": [{"status": "modified", "path": "safe.md"}],
        }
        with self.assertRaisesRegex(audit.AuditError, "allowlist_mismatch"):
            audit.audit_manifest(self.root, invalid)
        self.assertEqual(self.reads, [])

    def test_common_sensitive_file_stems_are_case_insensitive(self):
        for name in (
            "credentials.md", "secrets.md", "credentials.json", "TOKENS.MD",
            "Access_Token.JSON", "client-secret.md", "api_key.Md", "backup.PEM", ".netrc",
        ):
            with self.subTest(path=name):
                with self.assertRaisesRegex(audit.AuditError, "secret_path_refused"):
                    audit.validate_repo_path(name)
        # Path screening is deliberately filename-based, not a claim about arbitrary file contents.
        self.assertEqual(audit.validate_repo_path("guidance.md", markdown=True), "guidance.md")

    def test_reparse_guard_refusal_precedes_any_changed_file_read(self):
        original = audit._checked_path

        def guarded(root, name):
            if name == "unsafe.md":
                raise audit.AuditError("unsafe_path_refused")
            return original(root, name)

        self.add_file("safe.md", "safe\n")
        with patch.object(audit, "_checked_path", side_effect=guarded):
            with self.assertRaisesRegex(audit.AuditError, "unsafe_path_refused"):
                audit.audit_manifest(
                    self.root,
                    manifest([
                        {"status": "modified", "path": "safe.md"},
                        {"status": "modified", "path": "unsafe.md"},
                    ]),
                )
        self.assertEqual(self.reads, [])

    def test_duplicate_json_keys_types_and_manifest_limits_are_rejected(self):
        with self.assertRaisesRegex(audit.AuditError, "invalid_manifest_json"):
            audit.parse_manifest(b'{"schemaVersion":1,"schemaVersion":1,"allowedPaths":[],"changes":[]}')
        with self.assertRaisesRegex(audit.AuditError, "unsupported_manifest_version"):
            audit.validate_manifest({"schemaVersion": True, "allowedPaths": [], "changes": []})
        with self.assertRaisesRegex(audit.AuditError, "unsupported_manifest_version"):
            audit.parse_manifest(b'{"schemaVersion":2,"allowedPaths":[],"changes":[]}')
        with self.assertRaisesRegex(audit.AuditError, "manifest_too_large"):
            audit.parse_manifest(b"x" * (audit.MANIFEST_LIMIT + 1))
        too_many = [{"status": "deleted", "path": f"d{i}.md"} for i in range(audit.MAX_CHANGE_ENTRIES + 1)]
        with self.assertRaisesRegex(audit.AuditError, "manifest_limit_or_type"):
            audit.validate_manifest(manifest(too_many))

    def test_duplicate_occurrences_are_counted_without_retaining_all_locations(self):
        count = audit.MAX_DUPLICATE_LOCATIONS + 9
        self.add_file("repeat.md", "same line\n" * count)
        with patch.object(audit, "_location", wraps=audit._location) as location:
            result = audit.audit_manifest(
                self.root,
                manifest([{"status": "modified", "path": "repeat.md"}]),
            )
        candidate = next(item for item in result["findings"] if item["kind"] == "duplicate-candidate")
        self.assertEqual(candidate["occurrenceCount"], count)
        self.assertEqual(len(candidate["locations"]), audit.MAX_DUPLICATE_LOCATIONS)
        self.assertTrue(candidate["locationsTruncated"])
        self.assertEqual(location.call_count, audit.MAX_DUPLICATE_LOCATIONS)
        self.assertNotIn("same line", json.dumps(result))

    def test_changed_instruction_byte_limit_is_checked_before_reads(self):
        self.contents["large.md"] = b"x" * (audit.MAX_INSTRUCTION_BYTES + 1)
        self.exists.add("large.md")
        self.regular.add("large.md")
        with self.assertRaisesRegex(audit.AuditError, "instruction_file_too_large"):
            audit.audit_manifest(
                self.root,
                manifest([{"status": "modified", "path": "large.md"}]),
            )
        self.assertEqual(self.reads, [])

    def test_cli_emits_report_only_json_and_does_not_write_files(self):
        self.add_file("safe.md", "body\n")
        output = io.StringIO()
        report = {"schemaVersion": 1, "status": "report-only", "findings": []}
        with patch.object(audit, "run", return_value=report), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write attempted")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write attempted")), \
             redirect_stdout(output):
            audit.audit_manifest(
                self.root,
                manifest([{"status": "modified", "path": "safe.md"}]),
            )
            result = audit.main(["audit", "--root", "C:\\local\\repo", "--manifest", "changes.json"])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), report)


class InstructionAuditGuardBridgeTests(unittest.TestCase):
    def test_distribution_reparse_guard_refuses_before_source_read(self):
        root = Path(__file__).resolve().parents[1]
        target = root / "docs" / "ENGINEERING_LOOP.md"
        original = audit.distribution.is_link

        def simulate_reparse(path):
            if path == target:
                return True
            return original(path)

        with patch.object(audit.distribution, "is_link", side_effect=simulate_reparse):
            with patch.object(audit, "_read_path") as read:
                with self.assertRaisesRegex(audit.AuditError, "unsafe_path_refused"):
                    audit.audit_manifest(
                        root,
                        manifest([{"status": "modified", "path": "docs/ENGINEERING_LOOP.md"}]),
                    )
        read.assert_not_called()

    def test_sensitive_manifest_path_is_refused_before_root_or_file_access(self):
        with patch.object(audit.distribution, "checked_root", side_effect=AssertionError("root accessed")) as root:
            with patch.object(audit, "_read_path") as read:
                with self.assertRaisesRegex(audit.AuditError, "secret_path_refused"):
                    audit.run("unused-root", "credentials.JSON")
        root.assert_not_called()
        read.assert_not_called()

    def test_documented_manifest_argument_is_accepted_by_path_validator(self):
        document = Path("docs/ENGINEERING_LOOP.md").read_text(encoding="utf-8")
        section = document.split("Report-only аудит изменённых инструкций", 1)[1].split("## 6. Verify", 1)[0]
        manifest_path = ".harness/work/instruction-changes.json"
        self.assertIn(f"--manifest {manifest_path}", section)
        self.assertEqual(audit.validate_repo_path(manifest_path), manifest_path)


if __name__ == "__main__":
    unittest.main()
