#!/usr/bin/env python3
"""Bounded, offline summaries and typed result checks for Codex JSONL."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

import harness_metrics
from harness_distribution import DistributionError, checked_root, safe_path


MAX_BYTES = 2_000_000
MAX_LINE_BYTES = 64_000
MAX_EVENTS = 10_000
# ponytail: 2 MB ledger cap; add capped streaming only after a valid chain ledger exceeds this size.
MAX_METRIC_ROWS = 50_000
MAX_RESULT_BYTES = 256_000
MAX_SAFE_COUNTER = 10**4300 - 1
PROJECT_ROOT = Path(__file__).resolve().parent
TRACE_USAGE_FIELDS = {
    "input_tokens": "inputTokens",
    "cached_input_tokens": "cachedInputTokens",
    "output_tokens": "outputTokens",
    "reasoning_output_tokens": "reasoningOutputTokens",
}
RESULT_KEYS = {"status", "evidence", "checks", "unknown", "stopReason"}
RESULT_STATUSES = {"success", "partial", "blocked"}
STOP_REASONS = {"budget", "missing-evidence", "blocked", "user-input-required", "safety", "other"}
RESULT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}(?![\s\S])")
CHECK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(?![\s\S])")
EVIDENCE_REF = re.compile(r"^(?![Hh][Tt][Tt][Pp][Ss]?:|[Ff][Ii][Ll][Ee]:|[Jj][Aa][Vv][Aa][Ss][Cc][Rr][Ii][Pp][Tt]:|[Dd][Aa][Tt][Aa]:)[A-Za-z0-9][A-Za-z0-9._:-]{0,127}(?![\s\S])")
SECRET_COMPONENT = re.compile(r"(?i)(?:^\.env(?:$|\.)|^\.codex$|^\.aws$|^auth(?:\.json)?$|secret|credential|password|token)")


class CodexInputError(ValueError):
    """An input failure with a safe, non-content-bearing code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CodexInputError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise CodexInputError("invalid_json_number")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise CodexInputError("invalid_json_number")
    return result


def _decode_json(data: bytes) -> Any:
    try:
        source = data.decode("utf-8", errors="strict")
        return json.loads(
            source,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except CodexInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        raise CodexInputError("invalid_json") from None


def _validate_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/") or ":" in value:
        raise CodexInputError("unsafe_path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CodexInputError("unsafe_path")
    if any(part.endswith((" ", ".")) for part in parts):
        raise CodexInputError("unsafe_path")
    if any(SECRET_COMPONENT.search(part) for part in parts):
        raise CodexInputError("secret_path_refused")
    return value


def _read_bounded_file(root: Path, name: object, limit: int) -> bytes:
    relative = _validate_relative_path(name)
    try:
        target = safe_path(root, relative)
        if not target.is_file() or target.stat().st_size > limit:
            raise CodexInputError("file_unavailable_or_over_limit")
        with target.open("rb") as stream:
            data = stream.read(limit + 1)
    except CodexInputError:
        raise
    except (OSError, ValueError, TypeError, DistributionError):
        raise CodexInputError("file_unavailable_or_unsafe") from None
    if len(data) > limit:
        raise CodexInputError("file_grew_over_limit")
    return data


def _checked_root(root: str | Path) -> Path:
    try:
        return checked_root(root)
    except (OSError, ValueError, TypeError, DistributionError):
        raise CodexInputError("root_unavailable_or_unsafe") from None


def summarize_trace(root: str | Path, trace_path: str) -> dict[str, Any]:
    """Summarize observed counters from one bounded, explicitly selected trace."""
    local_root = _checked_root(root)
    raw = _read_bounded_file(local_root, trace_path, MAX_BYTES)
    if not raw:
        raise CodexInputError("empty_trace")
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if not lines or len(lines) > MAX_EVENTS:
        raise CodexInputError("event_count_over_limit_or_empty")

    events: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if line.endswith(b"\r"):
            line = line[:-1]
        if not line or len(line) > MAX_LINE_BYTES:
            raise CodexInputError("blank_or_overlong_line")
        event = _decode_json(line)
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise CodexInputError(f"invalid_event_{number}")
        events.append(event)

    starts = sum(event["type"] == "turn.started" for event in events)
    terminals = [event for event in events if event["type"] in {"turn.completed", "turn.failed"}]
    if starts != 1 or len(terminals) != 1:
        raise CodexInputError("trace_must_contain_one_turn")
    terminal = terminals[0]
    start_index = next(index for index, event in enumerate(events) if event["type"] == "turn.started")
    terminal_index = next(index for index, event in enumerate(events) if event is terminal)
    if start_index >= terminal_index or terminal_index != len(events) - 1:
        raise CodexInputError("invalid_turn_event_order")
    usage_occurrences = [event for event in events if "usage" in event]
    if any(event is not terminal for event in usage_occurrences) or len(usage_occurrences) > 1:
        raise CodexInputError("ambiguous_terminal_usage")

    unknown = ["model", "reasoningEffort", "durationMs", "acceptance"]
    usage: dict[str, int | None] = {field: None for field in TRACE_USAGE_FIELDS.values()}
    if not usage_occurrences:
        unknown.append("usage")
    else:
        source_usage = terminal["usage"]
        if not isinstance(source_usage, dict) or set(source_usage) - set(TRACE_USAGE_FIELDS):
            raise CodexInputError("invalid_usage_shape")
        for source_name, output_name in TRACE_USAGE_FIELDS.items():
            value = source_usage.get(source_name)
            if value is None:
                unknown.append(output_name)
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CodexInputError("invalid_usage_counter")
            elif value > MAX_SAFE_COUNTER:
                raise CodexInputError("usage_counter_over_limit")
            else:
                usage[output_name] = value
        cached = usage["cachedInputTokens"]
        reasoning = usage["reasoningOutputTokens"]
        if usage["inputTokens"] is not None and cached is not None and cached > usage["inputTokens"]:
            raise CodexInputError("cached_input_exceeds_input")
        if usage["outputTokens"] is not None and reasoning is not None and reasoning > usage["outputTokens"]:
            raise CodexInputError("reasoning_output_exceeds_output")

    input_tokens, output_tokens = usage["inputTokens"], usage["outputTokens"]
    if input_tokens is not None and output_tokens is not None:
        if output_tokens > MAX_SAFE_COUNTER - input_tokens:
            raise CodexInputError("usage_total_over_limit")
        total = input_tokens + output_tokens
    else:
        total = None
    if total is None:
        unknown.append("totalTokens")
    return {
        "schemaVersion": 1,
        "eventCount": len(events),
        "turnCount": 1,
        "terminalEvent": terminal["type"],
        "usage": {**usage, "totalTokens": total},
        "unknown": unknown,
    }


def _safe_evidence_reference(value: object) -> bool:
    return isinstance(value, str) and bool(EVIDENCE_REF.fullmatch(value))


def validate_result_shape(value: object) -> None:
    """Validate the fixed result shape only; this never evaluates acceptance."""
    if not isinstance(value, dict) or set(value) != RESULT_KEYS:
        raise CodexInputError("result_fields_invalid")
    if not isinstance(value["status"], str) or value["status"] not in RESULT_STATUSES:
        raise CodexInputError("result_status_invalid")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 32 or not all(_safe_evidence_reference(item) for item in evidence):
        raise CodexInputError("result_evidence_invalid")
    checks = value["checks"]
    if not isinstance(checks, dict) or len(checks) > 64:
        raise CodexInputError("result_checks_invalid")
    for key, result in checks.items():
        if not isinstance(key, str) or not CHECK_ID.fullmatch(key) or not isinstance(result, bool):
            raise CodexInputError("result_checks_invalid")
    unknown = value["unknown"]
    if not isinstance(unknown, list) or len(unknown) > 32 or any(not isinstance(item, str) or not RESULT_ID.fullmatch(item) for item in unknown):
        raise CodexInputError("result_unknown_invalid")
    reason = value["stopReason"]
    if reason is not None and (not isinstance(reason, str) or reason not in STOP_REASONS):
        raise CodexInputError("result_stop_reason_invalid")


def _budget_reason(
    passport: dict[str, Any],
    trusted_root: str | Path | None,
) -> str | None:
    chain = passport["chain"]
    if "runBudget" not in chain:
        return None
    budget = chain["runBudget"]
    required = {"maxAttempts", "maxTokens", "maxDurationMs"}
    if not isinstance(budget, dict) or set(budget) != required or any(
        isinstance(budget.get(field), bool) or not isinstance(budget.get(field), int) or budget[field] <= 0
        for field in required
    ):
        return "budget_invalid_configuration"

    try:
        expected_root = _checked_root(trusted_root or PROJECT_ROOT)
        declared_root = _checked_root(chain["projectRoot"])
    except (KeyError, CodexInputError):
        return "budget_root_unavailable"
    if os.path.normcase(os.path.normpath(str(expected_root))) != os.path.normcase(os.path.normpath(str(declared_root))):
        return "budget_foreign_root"

    try:
        metrics_name = _validate_relative_path(chain["metricsPath"])
        if not metrics_name.startswith(".harness/metrics/") or not metrics_name.endswith(".jsonl"):
            return "budget_invalid_metrics_path"
        raw = _read_bounded_file(expected_root, metrics_name, MAX_BYTES)
        if not raw:
            return "budget_no_matching_runs"
        raw_lines = raw.split(b"\n")
        if raw_lines and raw_lines[-1] == b"":
            raw_lines.pop()
        if len(raw_lines) > MAX_METRIC_ROWS:
            return "budget_metrics_over_limit"
        rows: list[dict[str, Any]] = []
        for line in raw_lines:
            if not line or len(line) > MAX_LINE_BYTES:
                return "budget_invalid_metrics"
            record = _decode_json(line)
            rows.append(harness_metrics.validate_record(record))
        selected = [row for row in rows if row["chainId"] == chain["chainId"]]
        if not selected:
            return "budget_no_matching_runs"
        if any(row["schemaVersion"] != harness_metrics.FAILURE_SCHEMA_VERSION for row in selected):
            return "budget_legacy_metrics"
        summary = harness_metrics.task_summary(selected, chain["chainId"])
    except (CodexInputError, ValueError, KeyError, TypeError, OSError, DistributionError):
        return "budget_invalid_metrics"

    if summary["tokens"]["total"] is None:
        return "budget_unknown_tokens"
    attempts = summary["attempts"]
    tokens = summary["tokens"]["total"]
    duration = sum(row["durationMs"] for row in selected)
    if attempts >= budget["maxAttempts"]:
        return "budget_max_attempts_reached"
    if tokens >= budget["maxTokens"]:
        return "budget_max_tokens_reached"
    if duration >= budget["maxDurationMs"]:
        return "budget_max_duration_reached"
    return None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness_codex.py")
    commands = parser.add_subparsers(dest="command", required=True)
    trace = commands.add_parser("trace-summary")
    trace.add_argument("input")
    trace.add_argument("--root", default=str(PROJECT_ROOT))
    result = commands.add_parser("validate-result")
    result.add_argument("input")
    result.add_argument("--root", default=str(PROJECT_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"trace-summary", "validate-result"}:
        try:
            root = _checked_root(args.root)
            if args.command == "trace-summary":
                result = summarize_trace(root, args.input)
            else:
                raw = _read_bounded_file(root, args.input, MAX_RESULT_BYTES)
                validate_result_shape(_decode_json(raw))
                result = {"shapeValid": True, "acceptance": "not_checked"}
            output = json.dumps(result, sort_keys=True, separators=(",", ":"))
        except CodexInputError as exc:
            print(json.dumps({"ok": False, "reason": exc.code}, separators=(",", ":")), file=sys.stderr)
            return 2
        except ValueError:
            print('{"ok":false,"reason":"output_serialization_failed"}', file=sys.stderr)
            return 2
        print(output)
        return 0

if __name__ == "__main__":
    raise SystemExit(main())
