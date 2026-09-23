from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import acceptance_gate
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
    def test_schema_two_failures_and_legacy_unknown(self):
        legacy = metrics.normalize_event(event())
        current = metrics.normalize_event(event(attempts=3, failedAttempts=2))
        self.assertEqual(legacy['schemaVersion'], 1)
        self.assertEqual(current['schemaVersion'], 2)
        self.assertNotIn('failedAttempts', metrics.validate_record(legacy))
        self.assertEqual(metrics.validate_record(current)['failedAttempts'], 2)
        for count in (-1, True, 4, '2'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                metrics.normalize_event(event(attempts=3, failedAttempts=count))
        for version in (True, 3):
            with self.subTest(version=version), self.assertRaises(ValueError):
                metrics.validate_record({**current, 'schemaVersion': version})

    def test_task_totals_do_not_confuse_partial_coverage_with_zero(self):
        records = [
            metrics.normalize_event(event(chainId='TASK', failedAttempts=1, accepted=False,
                                          inputTokens=10, outputTokens=5)),
            metrics.normalize_event(event(chainId='TASK', runId='run-2')),
            metrics.normalize_event(event(chainId='OTHER', failedAttempts=0,
                                          inputTokens=999, outputTokens=999)),
        ]
        result = metrics.task_summary(records, 'TASK')
        self.assertIsNone(result['tokens']['total'])
        self.assertEqual(result['tokens']['knownSubtotal'], 15)
        self.assertEqual(result['tokens']['knownCoverage'], 0.5)
        self.assertIsNone(result['failedAttempts']['total'])
        self.assertEqual(result['failedAttempts']['knownSubtotal'], 1)
        self.assertEqual(result['runs'], 2)
        self.assertIsNone(metrics.task_summary([], 'TASK')['tokens']['total'])
        with self.assertRaisesRegex(ValueError, 'duplicate runId'):
            metrics.task_summary(records + [records[0]], 'TASK')

    def test_task_complete_coverage_and_unknown_failures(self):
        record = metrics.normalize_event(event(chainId='TASK', failedAttempts=0,
                                               inputTokens=10, outputTokens=5))
        result = metrics.task_summary([record], 'TASK')
        self.assertEqual(result['tokens']['total'], 15)
        self.assertEqual(result['failedAttempts']['total'], 0)
        unknown = metrics.normalize_event(event(chainId='TASK', failedAttempts=None))
        self.assertIsNone(metrics.task_summary([unknown], 'TASK')['failedAttempts']['total'])

    def test_progress_reads_only_fresh_acceptance_never_executes_checks(self):
        fingerprint = {'algorithm': 'sha256', 'status': 'ok', 'value': 'a' * 64}
        manual = {'id': 'one', 'kind': 'manual', 'passes': True, 'evidence': 'checked',
                  'fingerprint': fingerprint}
        manual['definitionDigest'] = acceptance_gate.criterion_definition_digest(manual)
        gate = {'criteria': [
            manual,
            {'id': 'two', 'kind': 'command', 'command': 'DO-NOT-EXECUTE',
             'passes': True, 'evidence': 'old', 'fingerprint': {**fingerprint, 'value': 'b' * 64}},
            {'id': 'three', 'kind': 'manual', 'passes': False, 'evidence': ''},
        ]}
        with patch('acceptance_gate.load', return_value=gate), \
                patch('acceptance_gate.fingerprint', return_value=fingerprint), \
                patch('acceptance_gate.evaluate', side_effect=AssertionError('read only')):
            result = metrics.acceptance_progress('TASK')
        self.assertEqual(result['verified'], 1)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['percent'], 33.33)
        with patch('acceptance_gate.load', side_effect=FileNotFoundError()):
            self.assertIsNone(metrics.acceptance_progress('TASK')['percent'])
        for invalid in ([], None, {'criteria': []}):
            with self.subTest(gate=invalid), patch('acceptance_gate.load', return_value=invalid):
                self.assertIsNone(metrics.acceptance_progress('TASK')['percent'])

    def test_progress_does_not_count_changed_acceptance_definitions(self):
        fingerprint = {'algorithm': 'sha256', 'status': 'ok', 'value': 'a' * 64}
        command = {'id': 'check', 'kind': 'command', 'command': 'python old.py',
                   'passes': True, 'evidence': 'auto: exit 0', 'fingerprint': fingerprint}
        command['definitionDigest'] = acceptance_gate.command_definition_digest(command)
        command['command'] = 'python new.py'
        manual = {'id': 'review', 'kind': 'manual', 'description': 'Review old scope',
                  'passes': True, 'evidence': 'Reviewed', 'fingerprint': fingerprint}
        manual['definitionDigest'] = acceptance_gate.criterion_definition_digest(manual)
        manual['description'] = 'Approve new scope'
        with patch('acceptance_gate.load', return_value={'criteria': [command, manual]}), \
                patch('acceptance_gate.fingerprint', return_value=fingerprint), \
                patch('acceptance_gate.evaluate', side_effect=AssertionError('read only')):
            result = metrics.acceptance_progress('TASK')
        self.assertEqual(result['verified'], 0)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['percent'], 0.0)

    def test_task_cli_reads_mixed_schemas_without_mutation(self):
        test_root = Path(__file__).resolve().parents[1] / '.harness' / 'test-tmp'
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='metrics-', dir=test_root) as temporary:
            path = Path(temporary) / 'metrics.jsonl'
            command = [sys.executable, 'harness_metrics.py', 'task', '--file', str(path),
                       '--chain', 'CLI', '--work-item', 'missing-acceptance-fixture']
            empty = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(empty.returncode, 0, empty.stderr)
            missing = json.loads(empty.stdout)
            self.assertEqual(missing['telemetryStatus'], 'unavailable')
            self.assertIsNone(missing['tokens']['total'])
            self.assertIsNone(missing['progress']['percent'])
            metrics.append_record(path, metrics.normalize_event(event(chainId='CLI')))
            metrics.append_record(path, metrics.normalize_event(event(chainId='CLI', runId='run-2',
                                                                      failedAttempts=0)))
            before = path.read_bytes()
            completed = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result['runs'], 2)
            self.assertIsNone(result['failedAttempts']['total'])
            self.assertEqual(result['failedAttempts']['knownSubtotal'], 0)
            self.assertEqual(before, path.read_bytes())


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
        unknown = metrics.summary([normalized])
        self.assertIsNone(unknown["tokens"]["total"])

    def test_rejects_secret_and_multiline_identifiers(self):
        with self.assertRaisesRegex(ValueError, "secret-like"):
            metrics.validate_event(event(runId="token:abc"))
        with self.assertRaisesRegex(ValueError, "secret-like"):
            metrics.validate_event(event(model="password:hunter2"))
        with self.assertRaisesRegex(ValueError, "bounded identifier"):
            metrics.validate_event(event(runId="transcript excerpt for alice@example.com"))
        with self.assertRaisesRegex(ValueError, "bounded identifier"):
            metrics.validate_event(event(runId="alice@example.com"))
        with self.assertRaisesRegex(ValueError, "bounded identifier"):
            metrics.validate_event(event(pairKey="pair\n2"))

    def test_append_and_summary(self):
        temporary = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        path = Path(temporary.name)
        temporary.close()
        try:
            metrics.append_record(path, metrics.normalize_event(event(), "2026-08-03T00:00:00Z"))
            metrics.append_record(path, metrics.normalize_event(event(runId="run-2", inputTokens=3, outputTokens=5, released=True, used=True), "2026-08-03T00:01:00Z"))
            result = metrics.summary(metrics.iter_records(path))
        finally:
            path.unlink(missing_ok=True)
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

    def test_compare_has_a_bounded_sqlite_upgrade_path(self):
        records = [
            metrics.normalize_event(event(pairKey="a", treatment="base"), "2026-08-03T00:00:00Z"),
            metrics.normalize_event(event(runId="run-2", pairKey="b", treatment="base"), "2026-08-03T00:00:00Z"),
        ]
        with patch.object(metrics, "MAX_COMPARE_PAIR_KEYS", 1), self.assertRaisesRegex(ValueError, "SQLite index"):
            metrics.compare(iter(records), "base", "new")

    def test_cli_rejects_malformed_jsonl(self):
        temporary = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        path = Path(temporary.name)
        temporary.close()
        try:
            path.write_text("not-json\n", encoding="utf-8")
            completed = subprocess.run([sys.executable, "harness_metrics.py", "summary", "--file", str(path)], capture_output=True, text=True)
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("line 1", json.loads(completed.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
