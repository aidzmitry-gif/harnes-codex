#!/usr/bin/env python3
"""Bounded, offline summaries and typed result checks for Codex JSONL."""

from __future__ import annotations

import argparse
import hashlib
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
# ponytail: 4 MiB per native checkpoint read; expand after a larger bounded replay.
MAX_SESSION_BYTES = 4_000_000
SESSION_ANCHOR_BYTES = 4096
TOKEN_COUNT_MARKER = re.compile(rb'"type"\s*:\s*"token_count"')
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


def _session_anchor(stream: Any, offset: int) -> str:
    start = max(0, offset - SESSION_ANCHOR_BYTES)
    stream.seek(start)
    return hashlib.sha256(stream.read(offset - start)).hexdigest()


def summarize_session_usage(root: str | Path, session_path: str,
                            checkpoint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read a bounded native rollout slice; return only observed usage and an anchor.

    Initial history before the first counter in the tail is intentionally excluded.
    The anchor detects truncation/rotation/near-checkpoint edits, not arbitrary
    rewrites outside that anchor. Native rollouts must be append-only trusted logs.
    """
    local_root = _checked_root(root)
    relative = _validate_relative_path(session_path)
    try:
        target = safe_path(local_root, relative)
        if not target.is_file():
            raise CodexInputError('session_unavailable')
        with target.open('rb') as stream:
            info = os.fstat(stream.fileno())
            header = stream.readline(MAX_LINE_BYTES + 1)
            if len(header) > MAX_LINE_BYTES or not header.endswith(b'\n'):
                raise CodexInputError('session_header_over_limit_or_partial')
            metadata = _decode_json(header)
            payload = metadata.get('payload') if isinstance(metadata, dict) else None
            if not isinstance(metadata, dict) or metadata.get('type') != 'session_meta' or not isinstance(payload, dict):
                raise CodexInputError('unsupported_session_header')
            session_id = payload.get('id')
            source_id = hashlib.sha256(os.path.normcase(str(target)).encode('utf-8')).hexdigest()
            if not isinstance(session_id, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', session_id):
                raise CodexInputError('invalid_session_id')
            baseline = latest = None
            start_offset = end_offset = None
            bytes_read = len(header)
            if checkpoint is not None:
                harness_metrics.validate_usage_window(checkpoint)
                if checkpoint['sessionId'] != session_id or checkpoint['sourceId'] != source_id or checkpoint['endOffset'] > info.st_size:
                    raise CodexInputError('session_rotated_or_truncated')
                if _session_anchor(stream, checkpoint['endOffset']) != checkpoint['endAnchorSha256']:
                    raise CodexInputError('session_checkpoint_changed')
                bytes_read += min(checkpoint['endOffset'], SESSION_ANCHOR_BYTES)
                baseline = latest = checkpoint['endUsage']
                start_offset = end_offset = checkpoint['endOffset']
                position = checkpoint['endOffset']
            else:
                position = max(len(header), info.st_size - MAX_SESSION_BYTES)
            stream.seek(position)
            raw = stream.read(min(MAX_SESSION_BYTES, info.st_size - position))
            bytes_read += len(raw)
            has_more = position + len(raw) < info.st_size
            if position > len(header) and checkpoint is None:
                # A tail may start inside an arbitrary large non-usage event.
                raw_start = raw.find(b'\n') + 1
                if raw_start == 0:
                    raw = b''
                else:
                    raw = raw[raw_start:]
                    position += raw_start
            last_newline = raw.rfind(b'\n')
            raw = raw[:last_newline + 1] if last_newline >= 0 else b''
            event_count = 0
            cursor = position
            for record in raw.splitlines(keepends=True):
                cursor += len(record)
                if not TOKEN_COUNT_MARKER.search(record):
                    continue  # Never decode or emit chat/tool payloads.
                if len(record) > MAX_LINE_BYTES:
                    raise CodexInputError('session_usage_line_over_limit')
                event = _decode_json(record)
                payload = event.get('payload') if isinstance(event, dict) else None
                if not isinstance(event, dict) or event.get('type') != 'event_msg' or not isinstance(payload, dict) or payload.get('type') != 'token_count':
                    continue
                details = payload.get('info')
                if details is None:
                    continue
                if not isinstance(details, dict):
                    raise CodexInputError('invalid_session_usage')
                counters = details.get('total_token_usage')
                if not isinstance(counters, dict) or set(counters) - harness_metrics.USAGE_COUNTER_FIELDS - {'cache_write_input_tokens'}:
                    raise CodexInputError('unsupported_session_usage_fields')
                if 'cache_write_input_tokens' in counters:
                    written = counters['cache_write_input_tokens']
                    total_input = counters.get('input_tokens')
                    if type(written) is not int or type(total_input) is not int or not 0 <= written <= total_input:
                        raise CodexInputError('invalid_session_cache_write')
                # This observed optional subset is already inside input; no extra cost is inferred.
                current = harness_metrics.validate_cumulative_usage({key: counters[key] for key in harness_metrics.USAGE_COUNTER_FIELDS if key in counters})
                if latest is not None:
                    harness_metrics.validate_cumulative_usage({key: current[key] - latest[key]
                                                              for key in harness_metrics.USAGE_COUNTER_FIELDS})
                event_count += 1
                if event_count > MAX_EVENTS:
                    raise CodexInputError('session_event_limit')
                if baseline is None:
                    baseline, start_offset = current, cursor
                latest, end_offset = current, cursor
            usage = window = None
            if baseline is not None and latest is not None and latest['total_tokens'] > baseline['total_tokens']:
                usage = {output: latest[source] - baseline[source] for source, output in TRACE_USAGE_FIELDS.items()}
                usage['totalTokens'] = usage['inputTokens'] + usage['outputTokens']
                window = {'sessionId': session_id, 'sourceId': source_id, 'startOffset': start_offset, 'endOffset': end_offset,
                          'startUsage': baseline, 'endUsage': latest,
                          'endAnchorSha256': _session_anchor(stream, end_offset)}
                bytes_read += min(end_offset, SESSION_ANCHOR_BYTES)
                harness_metrics.validate_usage_window(window)
            if safe_path(local_root, relative).stat().st_ino != info.st_ino:
                raise CodexInputError('session_rotated_during_read')
    except CodexInputError:
        raise
    except (OSError, ValueError, TypeError, DistributionError):
        raise CodexInputError('invalid_or_unavailable_session_usage') from None
    return {'schemaVersion': 1, 'scope': 'single-session-observed-counter-delta',
            'usage': usage, 'usageWindow': window, 'bytesRead': bytes_read,
            'hasMore': has_more, 'counterEvents': event_count,
            'unknown': ['priorHistory', 'model', 'reasoningEffort', 'durationMs', 'acceptance', 'childUsage', 'billing']}


def record_session_usage(project_root: str | Path, event_path: str, metrics_path: str,
                         source_root: str | Path, session_path: str) -> dict[str, Any]:
    """Serialize cooperating importers; ledger checkpoints are the only resume state."""
    project = _checked_root(project_root)
    relative = _validate_relative_path(metrics_path)
    if not relative.startswith('.harness/metrics/') or not relative.endswith('.jsonl'):
        raise CodexInputError('invalid_metrics_path')
    event = _decode_json(_read_bounded_file(project, event_path, MAX_RESULT_BYTES))
    try:
        harness_metrics.validate_event(event)
        if event.get('inputTokens') is not None or event.get('outputTokens') is not None or harness_metrics.SESSION_FIELDS & set(event):
            raise CodexInputError('caller_usage_must_be_unknown')
        if event.get('chainId') is None:
            raise CodexInputError('session_chain_binding_required')
        ledger = safe_path(project, relative)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        lock = safe_path(project, relative.rsplit('/', 1)[0] + '/.session-import-lock')
        try:
            lock.mkdir()
        except FileExistsError:
            raise CodexInputError('session_metrics_locked') from None
        try:
            rows = []
            if ledger.exists():
                raw = _read_bounded_file(project, relative, MAX_BYTES)
                for row in raw.splitlines():
                    if not row or len(row) > MAX_LINE_BYTES:
                        raise CodexInputError('invalid_session_ledger')
                    rows.append(harness_metrics.validate_record(_decode_json(row)))
                    if len(rows) > MAX_METRIC_ROWS:
                        raise CodexInputError('session_ledger_over_limit')
            # Read identity separately, without scanning the body before resume.
            source = _checked_root(source_root)
            source_name = _validate_relative_path(session_path)
            with safe_path(source, source_name).open('rb') as stream:
                header = _decode_json(stream.readline(MAX_LINE_BYTES + 1))
            header_payload = header.get('payload') if isinstance(header, dict) else None
            if not isinstance(header_payload, dict):
                raise CodexInputError('unsupported_session_header')
            session_id = header_payload.get('id')
            source_id = hashlib.sha256(os.path.normcase(str(safe_path(source, source_name))).encode('utf-8')).hexdigest()
            matching = [row for row in rows if (row.get('usageWindow') or {}).get('sessionId') == session_id
                        or (row.get('usageWindow') or {}).get('sourceId') == source_id]
            if any(row['chainId'] != event.get('chainId') for row in matching):
                raise CodexInputError('session_chain_binding_changed')
            if len({row['runId'] for row in rows}) != len(rows):
                raise CodexInputError('duplicate_session_ledger_run')
            for chain_id in {row['chainId'] for row in matching}:
                harness_metrics.task_summary(matching, chain_id)
            checkpoint = matching[-1]['usageWindow'] if matching else None
            report = summarize_session_usage(source, source_name, checkpoint)
            if report['usage'] is None:
                return {'status': 'no-new-usage', 'hasMore': report['hasMore']}
            run_id = 'session:' + session_id + ':' + str(report['usageWindow']['endOffset'])
            if any(row['runId'] == run_id for row in rows):
                raise CodexInputError('duplicate_session_run')
            measured = {**event, **{key: value for key, value in report['usage'].items() if key != 'totalTokens'},
                        'runId': run_id, 'usageWindow': report['usageWindow']}
            record = harness_metrics.normalize_event(measured)
            harness_metrics.task_summary([*matching, record], event['chainId'])
            harness_metrics.append_record(ledger, record)
            return {'status': 'recorded', 'runId': run_id, 'usage': report['usage'],
                    'hasMore': report['hasMore'], 'acceptance': 'caller-declared-not-inferred'}
        finally:
            lock.rmdir()  # Only our own empty cooperating-writer lock.
    except CodexInputError:
        raise
    except (OSError, ValueError, TypeError, DistributionError):
        raise CodexInputError('session_import_failed') from None


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
        if any(row["schemaVersion"] not in (harness_metrics.FAILURE_SCHEMA_VERSION, harness_metrics.SESSION_SCHEMA_VERSION) for row in selected):
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
    session = commands.add_parser('session-summary')
    session.add_argument('input')
    session.add_argument('--root', required=True)
    importer = commands.add_parser('session-record')
    importer.add_argument('input')
    importer.add_argument('--source-root', required=True)
    importer.add_argument('--root', default=str(PROJECT_ROOT))
    importer.add_argument('--event', required=True)
    importer.add_argument('--metrics', required=True)
    result = commands.add_parser("validate-result")
    result.add_argument("input")
    result.add_argument("--root", default=str(PROJECT_ROOT))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"trace-summary", "validate-result", 'session-summary', 'session-record'}:
        try:
            root = _checked_root(args.root)
            if args.command == "trace-summary":
                result = summarize_trace(root, args.input)
            elif args.command == 'session-summary':
                result = summarize_session_usage(root, args.input)
            elif args.command == 'session-record':
                result = record_session_usage(root, args.event, args.metrics, args.source_root, args.input)
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
