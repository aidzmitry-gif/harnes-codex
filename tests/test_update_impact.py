import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update_impact


def valid_candidate():
    return {
        "schemaVersion": 1,
        "id": "codex-changelog-20260811",
        "product": "openai",
        "publishedDate": "2026-08-11",
        "sourceUrl": "https://learn.chatgpt.com/docs/changelog",
        "facts": ["Official changelog describes a Codex update."],
        "inferences": ["The update may affect local Harness workflows."],
        "assumptions": [],
        "impact": {"security": 0, "compatibility": 0, "userTime": 1, "reliability": 1, "implementationCost": 0},
        "affectedComponents": ["goal-runner"],
    }


class UpdateImpactTests(unittest.TestCase):
    def test_classifications_and_overrides(self):
        cases = (
            ("ignore", {"security": 0, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 1}, "ignore", "no-action"),
            ("evaluate", {"security": 0, "compatibility": 0, "userTime": 2, "reliability": 0, "implementationCost": 0}, "evaluate", "collect-more-evidence"),
            ("score-significant", {"security": 1, "compatibility": 0, "userTime": 1, "reliability": 1, "implementationCost": 0}, "significant", "run-local-evaluation"),
            ("security-override", {"security": 2, "compatibility": 0, "userTime": 0, "reliability": 0, "implementationCost": 3}, "significant", "run-local-evaluation"),
            ("compatibility-override", {"security": 0, "compatibility": 2, "userTime": 0, "reliability": 0, "implementationCost": 3}, "significant", "run-local-evaluation"),
        )
        for name, impact, classification, recommendation in cases:
            with self.subTest(name=name):
                candidate = valid_candidate(); candidate["impact"] = impact
                result = update_impact.classify(candidate)
                self.assertEqual(classification, result["classification"])
                self.assertEqual(recommendation, result["recommendation"])
                self.assertEqual(classification == "significant", result["significant"])

    def test_lists_keep_evidence_classes_separate_and_allow_empty_inference_assumption(self):
        candidate = valid_candidate(); candidate["inferences"] = []; candidate["assumptions"] = []
        self.assertEqual("evaluate", update_impact.classify(candidate)["classification"])
        for field, value in (("facts", []), ("facts", "not-a-list"), ("facts", ["x", "x"]), ("facts", ["x" * 501]), ("inferences", ["bad\nline"]), ("assumptions", ["x"] * 9)):
            with self.subTest(field=field, value=value):
                invalid = valid_candidate(); invalid[field] = value
                with self.assertRaises(update_impact.CandidateError):
                    update_impact.classify(invalid)

    def test_evidence_cannot_be_reused_across_classes(self):
        candidate = valid_candidate()
        candidate["inferences"] = [candidate["facts"][0]]
        candidate["assumptions"] = [candidate["facts"][0]]
        with self.assertRaises(update_impact.CandidateError):
            update_impact.classify(candidate)

    def test_strict_schema_and_scalar_validation(self):
        variants = []
        extra = valid_candidate(); extra["extra"] = "no"; variants.append(extra)
        missing = valid_candidate(); del missing["facts"]; variants.append(missing)
        for field, value in (("schemaVersion", True), ("schemaVersion", 2), ("id", "Uppercase"), ("id", "a" * 65), ("product", "other"), ("publishedDate", "2026-02-30"), ("affectedComponents", []), ("affectedComponents", ["x"] * 17), ("affectedComponents", ["UPPER"]), ("affectedComponents", ["same", "same"])):
            invalid = valid_candidate(); invalid[field] = value; variants.append(invalid)
        for dimension in update_impact.IMPACT_FIELDS:
            for value in (True, -1, 4, 1.0):
                invalid = valid_candidate(); invalid["impact"][dimension] = value; variants.append(invalid)
        for invalid in variants:
            with self.subTest(invalid=invalid):
                with self.assertRaises(update_impact.CandidateError):
                    update_impact.classify(invalid)

    def test_root_schema_version_requires_exact_integer(self):
        self.assertEqual("evaluate", update_impact.classify(valid_candidate())["classification"])
        for version in (True, 1.0):
            with self.subTest(version=version):
                candidate = valid_candidate(); candidate["schemaVersion"] = version
                with self.assertRaises(update_impact.CandidateError):
                    update_impact.classify(candidate)

    @patch("update_impact.Path.read_text")
    def test_classify_cli_rejects_non_integer_root_schema_version(self, read_text):
        read_text.return_value = json.dumps(valid_candidate())
        self.assertEqual(0, update_impact.main(["classify", "candidate.json"]))
        for version in (True, 1.0):
            with self.subTest(version=version):
                candidate = valid_candidate(); candidate["schemaVersion"] = version
                read_text.return_value = json.dumps(candidate)
                self.assertEqual(2, update_impact.main(["classify", "candidate.json"]))

    def test_url_allowlist_and_strict_url_forms(self):
        for hostname in sorted(update_impact.ALLOWED_HOSTS):
            candidate = valid_candidate(); candidate["sourceUrl"] = f"https://{hostname}/docs"
            update_impact.classify(candidate)
        candidate = valid_candidate(); candidate["sourceUrl"] = "https://learn.chatgpt.com/docs%20with%20space"
        update_impact.classify(candidate)
        for url in (
            "http://learn.chatgpt.com/docs", "https://evil.example/docs", "https://evil.learn.chatgpt.com/docs",
            "https://learn.chatgpt.com:443/docs", "https://learn.chatgpt.com:bad/docs", "https://user@learn.chatgpt.com/docs", "not-a-url",
            "", "https://learn.chatgpt.com/" + "a" * 10_000, " https://learn.chatgpt.com/docs", "\thttps://learn.chatgpt.com/docs",
            "https://learn.chatgpt.com/do cs", "https://learn.chatgpt.com/do\u00a0cs", "https://learn.chatgpt.com/do\tcs", "https://learn.chatgpt.com/do\rcs", "https://learn.chatgpt.com/do\ncs", "https://learn.chatgpt.com/\x00docs", "https://learn.chatgpt.com/\x7fdocs", "https://learn.chatgpt.com/\u0085docs", "https://learn.chatgpt.com/\u009fdocs",
        ):
            with self.subTest(url=url):
                candidate = valid_candidate(); candidate["sourceUrl"] = url
                with self.assertRaises(update_impact.CandidateError):
                    update_impact.classify(candidate)

    def test_classify_cli_rejects_whitespace_and_accepts_percent_encoded_space(self):
        cases = (("https://learn.chatgpt.com/docs\u00a0space", 2), ("https://learn.chatgpt.com/docs%20space", 0))
        for source_url, expected_code in cases:
            with self.subTest(source_url=source_url):
                candidate = valid_candidate(); candidate["sourceUrl"] = source_url
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
                    json.dump(candidate, handle)
                    path = Path(handle.name)
                try:
                    result = subprocess.run([sys.executable, "update_impact.py", "classify", str(path)], capture_output=True, text=True, check=False)
                finally:
                    path.unlink(missing_ok=True)
                self.assertEqual(expected_code, result.returncode)
                self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_cli_is_canonical_and_does_not_mutate_input(self):
        path = Path(__file__).parents[1] / "templates" / "update-candidate.example.json"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        command = [sys.executable, "update_impact.py", "classify", str(path)]
        first = subprocess.run(command, text=True, capture_output=True, check=False)
        second = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(first.stdout, json.dumps(json.loads(first.stdout), sort_keys=True, separators=(",", ":")) + "\n")
        self.assertEqual({"schemaVersion", "id", "classification", "significant", "score", "reasons", "affectedComponents", "recommendation"}, set(json.loads(first.stdout)))

    def test_cli_fails_closed(self):
        result = subprocess.run([sys.executable, "update_impact.py", "classify", "missing-candidate.json"], text=True, capture_output=True, check=False)
        self.assertEqual(2, result.returncode)
        self.assertTrue(result.stderr.startswith("FAIL INPUT: "))


if __name__ == "__main__":
    unittest.main()
