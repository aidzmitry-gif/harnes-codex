# Offline Codex trace and result checks

These commands only inspect the explicitly named local file. They do not scan
Codex sessions, invoke Codex, follow evidence references, or record telemetry.

```powershell
python -B .\harness_codex.py trace-summary .harness/fixtures/selected-trace.jsonl
python -B .\harness_codex.py validate-result .harness/fixtures/codex-result.json
python -B .\goal_orchestrator.py plan .harness/work/goal.passport.json --parent-state running
```

The trace command reports event/turn counts and only the recognized terminal
usage counters. Cached input and reasoning output are reported separately, not
added a second time. Missing observations remain `null` and are listed as
unknown. A trace must contain exactly one started turn and one terminal event;
input is limited to 2,000,000 bytes, 10,000 events, and 64,000 bytes per line.
Usage counters and their input-plus-output total must each fit 4,300 decimal
digits; larger values fail closed instead of risking a serializer error.
The report never includes prompts, commands, messages, raw tool output, model,
effort, duration, or an acceptance claim. The selected input uses a
POSIX-style repository-relative path; it must not traverse outside the local
project root or address a secret or reparse path.

`validate-result` checks the fixed shape in
[`templates/codex-result.schema.json`](../templates/codex-result.schema.json).
Evidence values are bounded identifiers, not links to open. Its success means
shape-valid only: output reports `acceptance: not_checked`; local acceptance
evidence remains a separate Harness check.

An optional chain `runBudget` contains exactly three positive integer limits:
`maxAttempts`, `maxTokens`, and `maxDurationMs`. Before recommending a ready
subgoal launch, the planner checks recorded schema-2 rows for the same chain in
its declared `.harness/metrics/*.jsonl` file. Reaching any limit, absent or
unknown required counters, duplicate run IDs, invalid rows, or an unavailable
ledger produces a machine-coded `hold` for future launches. The ledger and
passport are read-only. No budget preserves existing planning behavior;
active agents are not stopped or reclassified. The planner confirms the
passport root matches this checkout before reading a budget ledger.
The budget ledger must be at most 2,000,000 bytes and 50,000 rows; larger or
overlong data holds launch. If a valid chain ledger exceeds the byte cap, move
to a bounded streaming reader and expand the corresponding limits tests.

This is a gate over recorded run deltas, not proof the log covers all history,
not a cost estimate, and not evidence of live token savings.
