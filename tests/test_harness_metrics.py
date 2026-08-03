from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import harness_metrics as metrics


def event(**updates):
    value = {
        "runId": "run-1", "pairKey": "pair-1", "treatment": "baseline", "mode": "test",
        "durationMs": 100, "attempts": 1, "reworkCount": 0, "accepted": True,
        "escapedDefects": 0, "checksPassed": 2, "checksFailed": 0,
        "inputTokens": None, "outputTokens": None,
    }
    value.update(updates)
    return value


class HarnessMetricsTests(unittest.TestCase):
    def test_schema_validation_and_unknown_tokens(self):
        normalized = metrics.normalize_event(event(), "2026-08-03T00:00:00Z")
        self.assertEqual(normalized["schemaVersion"], 1)
        self.assertIsNone(normalized["inputTokens"])
        with self.assertRaisesRegex(ValueError, "unknown event"):
            metrics.validate_event(event(notes="no"))
        with self.assertRaisesRegex(ValueError, "both"):
            metrics.validate_event(event(inputTokens=2))
        with self.assertRaisesRegex(ValueError, "requires"):
            metrics.validate_event(event(released=False, used=True))

    def test_rejects_secret_and_multiline_identifiers(self):
        with self.assertRaisesRegex(ValueError, "secret-like"):
            metrics.validate_event(event(runId="token=abc"))
        with self.assertRaisesRegex(ValueError, "single-line"):
            metrics.validate_event(event(pairKey="pair\n2"))

    def test_append_and_summary(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "metrics.jsonl"
            metrics.append_record(path, metrics.normalize_event(event(), "2026-08-03T00:00:00Z"))
            metrics.append_record(path, metrics.normalize_event(event(runId="run-2", inputTokens=3, outputTokens=5, released=True, used=True), "2026-08-03T00:01:00Z"))
            result = metrics.summary(metrics.load_records(path))
        self.assertEqual(result["runs"], 2)
        self.assertEqual(result["tokens"]["knownRuns"], 1)
        self.assertEqual(result["tokens"]["total"], 8)
        self.assertEqual(result["release"]["rate"], 1.0)

    def test_paired_compare_and_exclusions(self):
        records = [
            metrics.normalize_event(event(pairKey="a", treatment="base", durationMs=100), "2026-08-03T00:00:00Z"),
            metrics.normalize_event(event(runId="run-2", pairKey="a", treatment="new", durationMs=80, accepted=False), "2026-08-03T00:00:00Z"),
            metrics.normalize_event(event(runId="run-3", pairKey="b", treatment="base"), "2026-08-03T00:00:00Z"),
        ]
        result = metrics.compare(records, "base", "new")
        self.assertEqual(result["pairs"], 1)
        self.assertEqual(result["exclusions"]["missingTreatment"], 1)
        self.assertEqual(result["deltas"]["durationMs"]["mean"], -20.0)
        self.assertEqual(result["deltas"]["accepted"]["mean"], -1.0)

    def test_cli_rejects_malformed_jsonl(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            completed = subprocess.run([sys.executable, "harness_metrics.py", "summary", "--file", str(path)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("line 1", json.loads(completed.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
