from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import harness_benchmark


FIXTURE = Path(__file__).parent / "fixtures" / "hre-001-benchmark.json"


def logical(report):
    value = copy.deepcopy(report)
    value.pop("measurement")
    for section in (value["quality"]["baseline"], value["quality"]["treatment"]):
        section.pop("durationMsMean")
    value["comparison"]["deltas"].pop("durationMs")
    return value


class HarnessBenchmarkTests(unittest.TestCase):
    def test_fixture_executes_twenty_exact_pairs_with_required_dimensions(self):
        report = harness_benchmark.run_fixture(FIXTURE)
        self.assertGreaterEqual(report["scenarioCount"], 20)
        self.assertEqual(report["scenarioCount"], report["pairCount"])
        self.assertEqual(0, sum(report["comparison"]["exclusions"].values()))
        self.assertEqual("unknown-no-model-runtime", report["tokenEvidence"]["status"])
        self.assertEqual(0, report["tokenEvidence"]["knownRuns"])
        self.assertIsNone(report["tokenEvidence"]["delta"])
        for mode in ("baseline", "treatment"):
            self.assertEqual(report["scenarioCount"], report["quality"][mode]["runs"])
            self.assertIn("escapedDefects", report["quality"][mode])
            self.assertIn("reworkTotal", report["quality"][mode])
            self.assertIn("release", report["quality"][mode])
            self.assertIn("usage", report["quality"][mode])
        self.assertIn("durationMs", report["measurement"])
        self.assertEqual(4, report["quality"]["baseline"]["accepted"])
        self.assertEqual(20, report["quality"]["treatment"]["accepted"])
        self.assertEqual(16, report["quality"]["baseline"]["escapedDefects"])
        self.assertEqual(0, report["quality"]["treatment"]["escapedDefects"])
        self.assertEqual(16, report["quality"]["baseline"]["reworkTotal"])
        self.assertEqual(0, report["quality"]["treatment"]["reworkTotal"])
        self.assertEqual(0.8, report["comparison"]["deltas"]["accepted"]["mean"])
        self.assertEqual(-0.8, report["comparison"]["deltas"]["defects"]["mean"])
        self.assertEqual(-0.8, report["comparison"]["deltas"]["rework"]["mean"])
        self.assertEqual(0.8, report["comparison"]["deltas"]["release"]["mean"])
        self.assertEqual(0.8, report["comparison"]["deltas"]["usage"]["mean"])

    def test_expected_contract_improvement_mismatch_is_caught(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["scenarios"][1]["expected"]["treatment"] = True
        temporary = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        path = Path(temporary.name)
        temporary.close()
        try:
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "regression mismatch"):
                harness_benchmark.run_fixture(path)
        finally:
            path.unlink(missing_ok=True)

    def test_two_runs_have_equal_non_time_logical_results(self):
        self.assertEqual(logical(harness_benchmark.run_fixture(FIXTURE)), logical(harness_benchmark.run_fixture(FIXTURE)))

    def test_unsafe_duplicate_and_short_fixtures_fail_closed(self):
        valid = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for mutation in (
            lambda data: data.update({"scenarios": data["scenarios"][:19]}),
            lambda data: data["scenarios"].append(copy.deepcopy(data["scenarios"][0])),
            lambda data: data["scenarios"][0].update({"command": "echo unsafe"}),
            lambda data: data["scenarios"][0].update({"id": "token=unsafe"}),
            lambda data: data["scenarios"][0].pop("shouldAccept"),
        ):
            candidate = copy.deepcopy(valid); mutation(candidate)
            path = Path(self.id().replace(".", "_") + ".json")
            try:
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaises(ValueError):
                    harness_benchmark.load_fixture(path)
            finally:
                path.unlink(missing_ok=True)

    def test_cli_prints_json(self):
        completed = subprocess.run([sys.executable, "harness_benchmark.py", "--fixture", str(FIXTURE)], capture_output=True, text=True, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(20, json.loads(completed.stdout)["scenarioCount"])


if __name__ == "__main__":
    unittest.main()
