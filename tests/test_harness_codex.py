import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness_codex
import harness_metrics
from goal_orchestrator import main as planner_main, plan_actions
from harness_codex import (
    CHECK_ID,
    EVIDENCE_REF,
    RESULT_ID,
    RESULT_STATUSES,
    STOP_REASONS,
    CodexInputError,
    MAX_SAFE_COUNTER,
    main,
    _validate_relative_path,
    summarize_trace,
    validate_result_shape,
    _decode_json,
)
from tests.test_goal_runner_validator import valid_passport


class TraceParsingTests(unittest.TestCase):
    def test_json_parser_rejects_duplicate_nonfinite_oversized_integer_and_deep_input(self):
        samples = [
            b'{"outer":{"x":1,"x":2}}',
            b"\xff",
            b'{"value":NaN}',
            b'{"value":1e400}',
            b'{"value":' + (b"9" * 5_000) + b"}",
            b"[" * 100_000 + b"0" + b"]" * 100_000,
        ]
        for source in samples:
            with self.subTest(length=len(source)), self.assertRaises(CodexInputError):
                _decode_json(source)

    def test_4300_digit_integer_is_within_parser_limit(self):
        parsed = _decode_json(b'{"value":' + b"9" * 4_300 + b"}")
        self.assertEqual(MAX_SAFE_COUNTER, parsed["value"])

    def test_windows_alias_components_are_rejected_before_path_access(self):
        for path in (".env ", ".codex./auth.json.", "AGENTS.md ", "docs./CODEX_EXEC.md"):
            with self.subTest(path=path), self.assertRaises(CodexInputError) as caught:
                _validate_relative_path(path)
            self.assertEqual("unsafe_path", caught.exception.code)


class TraceSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.trace_dir = self.root / ".harness" / "fixtures"
        self.trace_dir.mkdir(parents=True)
        self.trace_path = self.trace_dir / "selected.jsonl"
        self.relative_path = ".harness/fixtures/selected.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def write_trace(self, events):
        self.trace_path.write_bytes(b"\n".join(json.dumps(event).encode("utf-8") for event in events) + b"\n")

    def official_events(self):
        return [
            {"type": "thread.started", "thread_id": "fixture-thread"},
            {"type": "turn.started", "turn_id": "fixture-turn"},
            {"type": "item.started", "command": "DO_NOT_ECHO_PRIVATE_COMMAND"},
            {"type": "turn.completed", "usage": {
                "input_tokens": 120,
                "cached_input_tokens": 40,
                "output_tokens": 45,
                "reasoning_output_tokens": 8,
            }},
        ]

    def test_official_usage(self):
        self.write_trace(self.official_events())

        result = summarize_trace(self.root, self.relative_path)

        self.assertEqual(4, result["eventCount"])
        self.assertEqual(1, result["turnCount"])
        self.assertEqual({
            "inputTokens": 120,
            "cachedInputTokens": 40,
            "outputTokens": 45,
            "reasoningOutputTokens": 8,
            "totalTokens": 165,
        }, result["usage"])
        self.assertEqual(["model", "reasoningEffort", "durationMs", "acceptance"], result["unknown"])
        self.assertNotIn("DO_NOT_ECHO_PRIVATE_COMMAND", json.dumps(result))

    def test_missing_usage_stays_unknown_and_cli_never_claims_acceptance(self):
        self.write_trace(self.official_events()[:-1] + [{"type": "turn.completed"}])
        result = summarize_trace(self.root, self.relative_path)
        self.assertIsNone(result["usage"]["inputTokens"])
        self.assertIsNone(result["usage"]["totalTokens"])
        self.assertIn("usage", result["unknown"])

    def test_duplicate_nested_keys_unknown_usage_fields_and_bad_counters_fail_closed(self):
        bad_inputs = [
            b'{"type":"turn.started","payload":{"x":1,"x":2}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":2,"unknown":1}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":true}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":-1}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":NaN}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":1e400}}\n',
            b'{"type":"turn.completed","usage":{"input_tokens":' + (b"9" * 5_000) + b"}}\n",
        ]
        for payload in bad_inputs:
            with self.subTest(payload=payload[:30]):
                self.trace_path.write_bytes(b'{"type":"turn.started"}\n' + payload)
                with self.assertRaises(CodexInputError):
                    summarize_trace(self.root, self.relative_path)

    def test_repeat_terminal_multiturn_line_and_file_limits_fail_closed(self):
        cases = [
            self.official_events() + [{"type": "turn.failed"}],
            self.official_events()[:2] + [{"type": "turn.started"}] + self.official_events()[2:],
        ]
        for events in cases:
            with self.subTest(event_count=len(events)):
                self.write_trace(events)
                with self.assertRaises(CodexInputError):
                    summarize_trace(self.root, self.relative_path)

        self.trace_path.write_bytes(b"x" * 64_001 + b"\n")
        with self.assertRaises(CodexInputError):
            summarize_trace(self.root, self.relative_path)
        self.trace_path.write_bytes(b" " * (2_000_001))
        with self.assertRaises(CodexInputError):
            summarize_trace(self.root, self.relative_path)

    def test_turn_order_and_cached_or_reasoning_subcounts_fail_closed(self):
        for events in (
            [{"type": "turn.completed"}, {"type": "turn.started"}],
            [{"type": "turn.started"}, {"type": "turn.completed"}, {"type": "error"}],
            [{"type": "turn.started", "usage": {"input_tokens": 1}}, {"type": "turn.completed"}],
            [{"type": "turn.started"}, {"type": "turn.completed", "usage": {"input_tokens": 2, "cached_input_tokens": 3}}],
            [{"type": "turn.started"}, {"type": "turn.completed", "usage": {"output_tokens": 2, "reasoning_output_tokens": 3}}],
        ):
            with self.subTest(events=events):
                self.write_trace(events)
                with self.assertRaises(CodexInputError):
                    summarize_trace(self.root, self.relative_path)

        self.write_trace([{"type": "item.started"}] * 10_000 + [{"type": "turn.started"}, {"type": "turn.completed"}])
        with self.assertRaises(CodexInputError):
            summarize_trace(self.root, self.relative_path)

    def test_path_traversal_and_secret_paths_are_rejected(self):
        self.write_trace(self.official_events())
        for path in ("../outside.jsonl", ".codex/auth.json"):
            with self.subTest(path=path), self.assertRaises(CodexInputError):
                summarize_trace(self.root, path)

        aliases = (".env ", ".codex./auth.json.", "AGENTS.md ", "docs./CODEX_EXEC.md")
        for path in aliases:
            with self.subTest(alias=path), self.assertRaises(CodexInputError) as caught:
                summarize_trace(self.root, path)
            self.assertEqual("unsafe_path", caught.exception.code)

    def test_two_4300_digit_usage_counters_fail_with_safe_cli_reason(self):
        digits = b"9" * 4_300
        self.trace_path.write_bytes(
            b'{"type":"turn.started"}\n{"type":"turn.completed","usage":{"input_tokens":'
            + digits
            + b',"output_tokens":'
            + digits
            + b"}}\n"
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["trace-summary", self.relative_path, "--root", str(self.root)])
        self.assertEqual(2, code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual("usage_total_over_limit", json.loads(stderr.getvalue())["reason"])
        self.assertNotIn(digits.decode("ascii"), stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())


class CliSerializationTests(unittest.TestCase):
    def test_output_digit_limit_fails_closed(self):
        if not hasattr(sys, "get_int_max_str_digits"):
            self.skipTest("interpreter does not expose an integer digit limit")

        previous_limit = sys.get_int_max_str_digits()
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            sys.set_int_max_str_digits(640)
            with patch("harness_codex._checked_root", return_value=Path(".")), patch(
                "harness_codex.summarize_trace", return_value={"usage": {"totalTokens": 10**640}}
            ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["trace-summary", "fixture.jsonl"])
        finally:
            sys.set_int_max_str_digits(previous_limit)

        self.assertEqual(2, code)
        self.assertEqual("", stdout.getvalue())
        self.assertEqual(
            {"ok": False, "reason": "output_serialization_failed"},
            json.loads(stderr.getvalue()),
        )
        self.assertNotIn("Traceback", stderr.getvalue())


class ResultValidationTests(unittest.TestCase):
    def result(self):
        return {
            "status": "success",
            "evidence": ["C01:fixture"],
            "checks": {"type-check": False},
            "unknown": ["durationMs"],
            "stopReason": None,
        }

    def test_string_not_boolean(self):
        value = self.result()
        value["checks"]["type-check"] = "false"
        with self.assertRaisesRegex(CodexInputError, "result_checks_invalid"):
            validate_result_shape(value)

    def test_result_shape_and_schema_parity(self):
        validate_result_shape(self.result())
        schema_path = Path(__file__).resolve().parents[1] / "templates" / "codex-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(["status", "evidence", "checks", "unknown", "stopReason"], schema["required"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(RESULT_STATUSES, set(schema["properties"]["status"]["enum"]))
        self.assertEqual(32, schema["properties"]["evidence"]["maxItems"])
        self.assertEqual(EVIDENCE_REF.pattern, schema["properties"]["evidence"]["items"]["pattern"])
        self.assertEqual(128, schema["properties"]["evidence"]["items"]["maxLength"])
        self.assertEqual(64, schema["properties"]["checks"]["maxProperties"])
        self.assertEqual(64, schema["properties"]["checks"]["propertyNames"]["maxLength"])
        self.assertEqual(32, schema["properties"]["unknown"]["maxItems"])
        self.assertEqual(RESULT_ID.pattern, schema["properties"]["unknown"]["items"]["pattern"])
        self.assertEqual(CHECK_ID.pattern, schema["properties"]["checks"]["propertyNames"]["pattern"])
        self.assertEqual(STOP_REASONS | {None}, set(schema["properties"]["stopReason"]["enum"]))

    def test_unknown_properties_and_unsafe_references_are_rejected(self):
        value = self.result()
        value["accepted"] = True
        with self.assertRaises(CodexInputError):
            validate_result_shape(value)

    def test_schema_search_patterns_reject_trailing_newlines(self):
        schema_path = Path(__file__).resolve().parents[1] / "templates" / "codex-result.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        samples = (
            (schema["properties"]["evidence"]["items"]["pattern"], "C01\n"),
            (schema["properties"]["checks"]["propertyNames"]["pattern"], "unit\n"),
            (schema["properties"]["unknown"]["items"]["pattern"], "reason\n"),
        )
        for pattern, value in samples:
            with self.subTest(value=value):
                self.assertIsNone(re.search(pattern, value))

        result = self.result()
        result["evidence"] = ["C01\n"]
        with self.assertRaises(CodexInputError):
            validate_result_shape(result)
        result = self.result()
        result["checks"] = {"unit\n": True}
        with self.assertRaises(CodexInputError):
            validate_result_shape(result)
        result = self.result()
        result["unknown"] = ["reason\n"]
        with self.assertRaises(CodexInputError):
            validate_result_shape(result)

    def test_windows_alias_path_is_rejected_by_result_cli_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main(["validate-result", "AGENTS.md ", "--root", directory])
            self.assertEqual(2, code)
            self.assertEqual("unsafe_path", json.loads(stderr.getvalue())["reason"])
        value = self.result()
        value["evidence"] = ["https://example.invalid"]
        with self.assertRaises(CodexInputError):
            validate_result_shape(value)

    def test_cli_reports_shape_separately_from_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / ".harness" / "fixtures" / "result.json"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps(self.result()), encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["validate-result", ".harness/fixtures/result.json", "--root", str(root)])
            self.assertEqual(0, code)
            self.assertEqual({"shapeValid": True, "acceptance": "not_checked"}, json.loads(stdout.getvalue()))


class BudgetGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.metrics_path = self.root / ".harness" / "metrics" / "runs.jsonl"
        self.metrics_path.parent.mkdir(parents=True)
        self.passport = valid_passport()
        self.passport["agents"] = []
        self.passport["chain"]["projectRoot"] = str(self.root)
        self.passport["chain"]["metricsPath"] = ".harness/metrics/runs.jsonl"
        self.passport["chain"]["runBudget"] = {"maxAttempts": 3, "maxTokens": 16, "maxDurationMs": 121}

    def tearDown(self):
        self.temp.cleanup()

    def record(self, *, run_id="budget-run-1", chain_id=None, version=2, input_tokens=10, output_tokens=5, attempts=2, duration=120):
        chain_id = chain_id or self.passport["chain"]["chainId"]
        event = {
            "runId": run_id,
            "pairKey": "budget-pair-1",
            "chainId": chain_id,
            "subgoalId": "G02",
            "treatment": "budget-test",
            "mode": "local",
            "model": "gpt-6-luna",
            "reasoningEffort": "xhigh",
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "durationMs": duration,
            "attempts": attempts,
            "reworkCount": 0,
            "accepted": False,
            "released": None,
            "used": None,
            "escapedDefects": 0,
            "checksPassed": 0,
            "checksFailed": 0,
        }
        if version == 2:
            event["failedAttempts"] = 0
        return harness_metrics.normalize_event(event, "2026-10-03T00:00:00Z")

    def write_records(self, *records):
        self.metrics_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in records), encoding="utf-8")

    def actions(self, passport=None):
        return plan_actions(passport or self.passport, "running", trusted_root=self.root)["actions"]

    def test_budget_limits_exact_and_over(self):
        self.write_records(self.record())
        reasons = {
            "maxAttempts": "budget_max_attempts_reached",
            "maxTokens": "budget_max_tokens_reached",
            "maxDurationMs": "budget_max_duration_reached",
        }
        for field, observed in (("maxAttempts", 2), ("maxTokens", 15), ("maxDurationMs", 120)):
            with self.subTest(field=field, threshold="below"):
                self.passport["chain"]["runBudget"].update(maxAttempts=3, maxTokens=16, maxDurationMs=121)
                self.assertEqual(["launch"], [item["action"] for item in self.actions()])
            with self.subTest(field=field, threshold="exact"):
                self.passport["chain"]["runBudget"][field] = observed
                action = self.actions()[0]
                self.assertEqual("hold", action["action"])
                self.assertEqual(reasons[field], action["reason"])
            with self.subTest(field=field, threshold="over"):
                self.passport["chain"]["runBudget"][field] = observed - 1
                self.assertEqual(reasons[field], self.actions()[0]["reason"])

    def test_schema3_usage_reaches_existing_budget_guard_without_counting_subsets_twice(self):
        value = dict(self.record())
        value.pop('schemaVersion')
        value.pop('recordedAt')
        value.update(cachedInputTokens=8, reasoningOutputTokens=3)
        self.write_records(harness_metrics.normalize_event(value))
        self.passport['chain']['metricsSchemaVersion'] = 3
        self.assertEqual('launch', self.actions()[0]['action'])
        self.passport['chain']['runBudget']['maxTokens'] = 15
        self.assertEqual('budget_max_tokens_reached', self.actions()[0]['reason'])

    def test_unknown_legacy_duplicate_foreign_and_unavailable_evidence_hold(self):
        cases = [
            (self.record(input_tokens=None, output_tokens=None),),
            (self.record(version=1),),
            (self.record(), self.record(run_id="budget-run-1")),
            (self.record(chain_id="FOREIGN-CHAIN"),),
        ]
        for records in cases:
            with self.subTest(records=len(records), schema=records[0]["schemaVersion"]):
                self.write_records(*records)
                self.assertEqual("hold", self.actions()[0]["action"])
        self.metrics_path.unlink()
        self.assertEqual("hold", self.actions()[0]["action"])

    def test_budget_root_mismatch_holds_and_no_budget_remains_compatible(self):
        self.write_records(self.record())
        self.passport["chain"]["projectRoot"] = str(self.root.parent)
        self.assertEqual("budget_foreign_root", self.actions()[0]["reason"])
        self.passport["chain"].pop("runBudget")
        self.assertEqual("launch", self.actions()[0]["action"])

    def test_budget_hold_preserves_wait_for_running_agent(self):
        self.write_records(self.record(attempts=3))
        self.passport["chain"]["runBudget"]["maxAttempts"] = 3
        self.passport["subgoals"].append({"id": "G03", "dependsOn": ["G01"], "wave": 3, "status": "ready", "execution": "subagent", "model": "terra", "worktree": "g03", "ownedPaths": ["g03.py"]})
        self.passport["agents"] = [{"id": "active", "subgoalId": "G02", "role": "worker", "depth": 1, "worktree": "g02", "ownedPaths": ["x.py"], "status": "active", "writer": True}]
        actions = self.actions()
        self.assertIn(("wait", "agent_active"), [(item["action"], item["reason"]) for item in actions])
        self.assertIn(("hold", "budget_max_attempts_reached"), [(item["action"], item["reason"]) for item in actions])

    def test_cli_rejects_duplicate_nested_budget_key_without_launch(self):
        self.passport["chain"]["runBudget"]["maxTokens"] = 15
        self.write_records(self.record())
        passport_path = self.root / ".harness" / "work" / "passport.json"
        passport_path.parent.mkdir(parents=True)
        source = json.dumps(self.passport, separators=(",", ":"))
        replacements = source.count('"maxTokens":15')
        source = source.replace('"maxTokens":15', '"maxTokens":15,"maxTokens":1000')
        self.assertEqual(1, replacements)
        passport_path.write_text(source, encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = planner_main(
                ["plan", str(passport_path), "--parent-state", "running"],
                trusted_root=self.root,
            )

        self.assertEqual(2, code)
        self.assertNotIn("launch", stdout.getvalue())
        self.assertNotIn("1000", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_budget_rejects_windows_alias_path_before_read(self):
        self.passport["chain"]["metricsPath"] = ".harness/metrics/ledger./runs.jsonl"
        action = self.actions()[0]
        self.assertEqual("hold", action["action"])
        self.assertEqual("budget_invalid_metrics", action["reason"])
