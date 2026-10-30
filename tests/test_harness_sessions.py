"""Bounded native-session usage: no transcript output, guesses or double counting."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import unittest
import uuid
from unittest.mock import patch

import harness_codex as codex
import harness_metrics as metrics
from tests.test_harness_metrics import event


SESSION_ID = '019fca39-7a3e-7a90-a726-a47e3c72dc19'


def usage(input_tokens=100, cached=80, output=10, reasoning=5):
    return {'input_tokens': input_tokens, 'cached_input_tokens': cached, 'output_tokens': output,
            'reasoning_output_tokens': reasoning, 'total_tokens': input_tokens + output}


def line(value):
    return (json.dumps(value, separators=(',', ':')) + '\n').encode('utf-8')


def count(value):
    return line({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {'total_token_usage': value}}})


class NativeUsageTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / '.harness' / 'test-tmp' / ('sessions-' + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.root)
        self.source = self.root / 'source'
        self.project = self.root / 'project'
        self.source.mkdir()
        self.project.mkdir()
        self.log = self.source / 'rollout.jsonl'
        self.event_file = self.project / 'event.json'
        self.event_file.write_text(json.dumps(event(chainId='HRE-013', subgoalId='G01', failedAttempts=0)), encoding='utf-8')
        self.header = line({'type': 'session_meta', 'payload': {'id': SESSION_ID}})
        self.before, self.after = usage(), usage(150, 110, 40, 20)
        self.log.write_bytes(self.header + count(self.before) + count(self.after))
        self.ledger = self.project / '.harness' / 'metrics' / 'test.jsonl'

    def record(self):
        return codex.record_session_usage(self.project, 'event.json', '.harness/metrics/test.jsonl', self.source, 'rollout.jsonl')

    def test_summary_is_a_delta_not_the_cumulative_total_or_transcript(self):
        private_event = b'{"type":"response_item","payload":{"text":"PRIVATE_NEVER_PRINT"}}\n'
        self.log.write_bytes(self.header + count(self.before) + private_event + count(self.after))
        report = codex.summarize_session_usage(self.source, 'rollout.jsonl')
        self.assertEqual(report['usage'], {'inputTokens': 50, 'cachedInputTokens': 30,
                         'outputTokens': 30, 'reasoningOutputTokens': 15, 'totalTokens': 80})
        self.assertNotIn('PRIVATE', json.dumps(report))
        self.assertEqual(report['scope'], 'single-session-observed-counter-delta')

    def test_incremental_record_repeat_and_resume_are_nonoverlapping(self):
        result = self.record()
        self.assertEqual(result['status'], 'recorded')
        original = self.ledger.read_bytes()
        self.assertEqual(self.record()['status'], 'no-new-usage')
        self.assertEqual(self.ledger.read_bytes(), original)
        with self.log.open('ab') as stream:
            stream.write(count(usage(200, 140, 70, 35)))
        self.assertEqual(self.record()['status'], 'recorded')
        rows = metrics.load_records(self.ledger)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['schemaVersion'], 3)
        self.assertEqual(rows[1]['usageWindow']['startOffset'], rows[0]['usageWindow']['endOffset'])
        result = metrics.task_summary(rows, 'HRE-013')
        self.assertEqual(result['tokens']['total'], 160)
        self.assertEqual(result['cachedInputTokens']['total'], 60)
        self.assertEqual(result['reasoningOutputTokens']['total'], 30)

    def test_one_counter_and_info_none_are_unknown_not_zero(self):
        self.log.write_bytes(self.header + count(self.before) + line({'type': 'event_msg', 'payload': {'type': 'token_count', 'info': None}}))
        result = codex.summarize_session_usage(self.source, 'rollout.jsonl')
        self.assertIsNone(result['usage'])
        self.assertEqual(self.record()['status'], 'no-new-usage')
        self.assertFalse(self.ledger.exists())

    def test_observed_cache_write_field_is_validated_not_added_to_total(self):
        self.log.write_bytes(self.header + count({**self.before, 'cache_write_input_tokens': 0})
                             + count({**self.after, 'cache_write_input_tokens': 0}))
        self.assertEqual(codex.summarize_session_usage(self.source, 'rollout.jsonl')['usage']['totalTokens'], 80)
        for extra in ({'cache_write_input_tokens': True}, {'cache_write_input_tokens': 999}, {'unexpected_counter': 0}):
            self.log.write_bytes(self.header + count(self.before) + count({**self.after, **extra}))
            with self.subTest(extra=extra), self.assertRaises(codex.CodexInputError):
                codex.summarize_session_usage(self.source, 'rollout.jsonl')

    def test_reset_invalid_subset_total_and_boolean_fail_before_record(self):
        for invalid in (usage(50, 30, 5, 2), usage(110, 105, 20, 10),
                        {**self.after, 'total_tokens': 0}, {**self.after, 'input_tokens': True}):
            with self.subTest(invalid=invalid):
                self.log.write_bytes(self.header + count(self.before) + count(invalid))
                with self.assertRaises(codex.CodexInputError):
                    self.record()
                self.assertFalse(self.ledger.exists())

    def test_incomplete_tail_waits_without_losing_checkpoint(self):
        self.record()
        prior = self.ledger.read_bytes()
        extra = count(usage(200, 140, 70, 35))
        with self.log.open('ab') as stream:
            stream.write(extra[:-1])
        self.assertEqual(self.record()['status'], 'no-new-usage')
        self.assertEqual(self.ledger.read_bytes(), prior)
        with self.log.open('ab') as stream:
            stream.write(b'\n')
        self.assertEqual(self.record()['status'], 'recorded')

    def test_rotation_truncation_and_anchor_change_refuse_resume(self):
        self.record()
        original_log, ledger = self.log.read_bytes(), self.ledger.read_bytes()
        for changed in (original_log[:len(self.header)], original_log.replace(SESSION_ID.encode(), b'119fca39-7a3e-7a90-a726-a47e3c72dc19'),
                        original_log.replace(b'"cached_input_tokens":80', b'"cached_input_tokens":81')):
            with self.subTest(kind=len(changed)):
                self.log.write_bytes(changed)
                with self.assertRaises(codex.CodexInputError):
                    self.record()
                self.assertEqual(self.ledger.read_bytes(), ledger)

    def test_cross_chain_and_existing_writer_lock_refuse(self):
        self.record()
        self.event_file.write_text(json.dumps(event(chainId='OTHER', failedAttempts=0)), encoding='utf-8')
        with self.assertRaises(codex.CodexInputError):
            self.record()
        self.event_file.write_text(json.dumps(event(chainId='HRE-013', failedAttempts=0)), encoding='utf-8')
        lock = self.ledger.parent / '.session-import-lock'
        lock.mkdir()
        with self.assertRaises(codex.CodexInputError):
            self.record()
        self.assertTrue(lock.is_dir())

    def test_privacy_paths_and_caller_fabricated_tokens_refuse(self):
        for name in ('../rollout.jsonl', '.env', '.codex/auth.json', 'secrets/log.jsonl'):
            with self.subTest(name=name), self.assertRaises(codex.CodexInputError):
                codex.summarize_session_usage(self.source, name)
        self.event_file.write_text(json.dumps(event(inputTokens=999, outputTokens=999)), encoding='utf-8')
        with self.assertRaises(codex.CodexInputError):
            self.record()
        self.assertFalse(self.ledger.exists())

    def test_large_prefix_is_not_scanned_and_overlong_usage_refuses(self):
        filler = line({'type': 'response_item', 'payload': {'text': 'x' * 3000}})
        self.log.write_bytes(self.header + filler + count(self.before) + count(self.after))
        with patch.object(codex, 'MAX_SESSION_BYTES', 1000):
            report = codex.summarize_session_usage(self.source, 'rollout.jsonl')
        self.assertEqual(report['usage']['totalTokens'], 80)
        self.assertLessEqual(report['bytesRead'], len(self.header) + 1000 + codex.SESSION_ANCHOR_BYTES)
        self.log.write_bytes(self.header + count(self.before) + count({**self.after, 'extra': 'x' * codex.MAX_LINE_BYTES}))
        with self.assertRaises(codex.CodexInputError):
            codex.summarize_session_usage(self.source, 'rollout.jsonl')

    def test_cli_only_emits_safe_summary_or_error_codes(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = codex.main(['session-summary', 'rollout.jsonl', '--root', str(self.source)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['usage']['totalTokens'], 80)
        self.assertEqual(stderr.getvalue(), '')
        stdout, stderr = io.StringIO(), io.StringIO()
        self.log.write_bytes(b'{private malformed header\n')
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = codex.main(['session-summary', 'rollout.jsonl', '--root', str(self.source)])
        self.assertEqual(code, 2)
        self.assertNotIn('private', stderr.getvalue())

    def test_header_type_failures_and_copied_source_do_not_leak_or_reimport(self):
        original = self.log.read_bytes()
        for header in ([], {'type': 'session_meta', 'payload': []}, {'type': 'other', 'payload': {'id': SESSION_ID}}):
            self.log.write_bytes(line(header) + count(self.before) + count(self.after))
            with self.subTest(header=header), self.assertRaises(codex.CodexInputError):
                codex.summarize_session_usage(self.source, 'rollout.jsonl')
        self.log.write_bytes(original)
        self.record()
        (self.source / 'copy.jsonl').write_bytes(original)
        with self.assertRaises(codex.CodexInputError):
            codex.record_session_usage(self.project, 'event.json', '.harness/metrics/test.jsonl', self.source, 'copy.jsonl')

    def test_existing_schema3_non_session_row_and_duplicate_ledger(self):
        self.ledger.parent.mkdir(parents=True)
        metrics.append_record(self.ledger, metrics.normalize_event(event(chainId='HRE-013',
                              runId='older', inputTokens=100, outputTokens=40, cachedInputTokens=80)))
        self.assertEqual(self.record()['status'], 'recorded')
        content = self.ledger.read_bytes()
        self.ledger.write_bytes(content + content)
        with self.assertRaises(codex.CodexInputError):
            self.record()

    def test_task_summary_refuses_unverified_parent_child_aggregation(self):
        self.record()
        row = metrics.load_records(self.ledger)[0]
        other = json.loads(json.dumps(row))
        other['runId'] = 'other-session'
        other['usageWindow']['sessionId'] = '119fca39-7a3e-7a90-a726-a47e3c72dc19'
        other['usageWindow']['sourceId'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'multiple native sessions'):
            metrics.task_summary([row, other], 'HRE-013')

    def test_cli_record_uses_explicit_roots_and_event_but_not_caller_token_guesses(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = codex.main(['session-record', 'rollout.jsonl', '--source-root', str(self.source),
                               '--root', str(self.project), '--event', 'event.json', '--metrics', '.harness/metrics/test.jsonl'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['status'], 'recorded')
        self.assertNotIn(str(self.source), stdout.getvalue())


class UsageSchemaTests(unittest.TestCase):
    def test_old_schemas_remain_exact_and_new_subsets_are_not_added_to_total(self):
        old = metrics.normalize_event(event(chainId='C'))
        new = metrics.normalize_event(event(chainId='C', runId='r2', failedAttempts=0,
                 inputTokens=100, outputTokens=40, cachedInputTokens=80, reasoningOutputTokens=20))
        self.assertEqual(old['schemaVersion'], 1)
        self.assertEqual(new['schemaVersion'], 3)
        metrics.validate_record(old)
        metrics.validate_record(new)
        result = metrics.task_summary([old, new], 'C')
        self.assertIsNone(result['tokens']['total'])
        self.assertEqual(result['tokens']['knownSubtotal'], 140)
        self.assertEqual(result['cachedInputTokens']['knownSubtotal'], 80)
        self.assertIsNone(result['cachedInputTokens']['total'])

    def test_bad_subsets_are_rejected(self):
        for fields in ({'cachedInputTokens': 101}, {'reasoningOutputTokens': 41},
                       {'cachedInputTokens': True}, {'cachedInputTokens': -1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                metrics.normalize_event(event(inputTokens=100, outputTokens=40, **fields))

    def test_cache_and_reasoning_compare_have_independent_coverage(self):
        before = metrics.normalize_event(event(inputTokens=100, outputTokens=40,
                    cachedInputTokens=80, reasoningOutputTokens=20))
        after = metrics.normalize_event(event(treatment='new', runId='new', inputTokens=90, outputTokens=30,
                    cachedInputTokens=70, reasoningOutputTokens=15))
        report = metrics.compare([before, after], 'baseline', 'new')
        self.assertEqual(report['deltas']['knownTotalTokens']['mean'], -20)
        self.assertEqual(report['deltas']['uncachedInputTokens']['mean'], 0)
        self.assertEqual(report['deltas']['reasoningOutputTokens']['mean'], -5)
        self.assertEqual(metrics.summary([before, after])['tokens']['cachedInput'], 150)


if __name__ == '__main__':
    unittest.main()
