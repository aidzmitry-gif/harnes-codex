# Task report: usage, failed attempts, acceptance

Use the existing `harness_metrics.py` and `acceptance_gate.py`, not another journal.
Before running, record baseline/treatment IDs and the task's complete acceptance
criteria (including integration/security/production where in scope). The gate is
the denominator: do not remove a failed criterion merely to raise the percentage.

## Record a meaningful checkpoint

Minimal schema-2 event example (replace identifiers and observed counts):

```json
{
  "runId": "TASK-001-G02-attempt-1",
  "pairKey": "TASK-001-G02-test",
  "chainId": "TASK-001",
  "subgoalId": "G02",
  "treatment": "luna-astra-v1",
  "mode": "implementation",
  "model": "gpt-6-luna",
  "reasoningEffort": "xhigh",
  "inputTokens": null,
  "outputTokens": null,
  "durationMs": 1200,
  "attempts": 1,
  "failedAttempts": 1,
  "reworkCount": 0,
  "accepted": false,
  "released": false,
  "used": false,
  "escapedDefects": 0,
  "checksPassed": 0,
  "checksFailed": 1
}
```

An attempt is one bounded execution/verification of the agreed outcome. Record a
failed attempt when that execution fails its acceptance, including an environment
failure; record the reason in the work item, not the structured metrics. Expected
red tests used as an oracle, individual failed assertions, and unexecuted proposals
are not additional attempts. `failedAttempts <= attempts`; use `null` when unknown.
Successful retries are separate run IDs. Emit only incremental usage since the
last checkpoint, never both a child's usage and an inclusive parent total. Output
usage already includes any reasoning tokens included by the runtime; do not add
them a second time. Account-wide quota percentages are not task token usage.

`record` writes schema 2 when `failedAttempts` is present, otherwise legacy schema
1. New readers accept both; old readers must be updated before using schema 2.
Set new passports' `metricsSchemaVersion` to 2; do not rewrite historical JSONL.
Keep a single writer. A duplicate run ID makes `task` fail closed rather than
silently count the same work twice. Do not delete failed records to improve scores.

## Report

```text
python harness_metrics.py task --file .harness/metrics/TASK-001.jsonl --chain TASK-001 --work-item task-001
```

Use the CLI installed in the project being measured (the gate root is the directory
containing `acceptance_gate.py`, not an arbitrary cwd). The command is read-only: it reads stored
acceptance evidence and the current repository fingerprint, never runs a check.
It counts only matching chain IDs. `total` is null if any recorded run lacks that
metric; `knownSubtotal` and `knownCoverage` explain partial evidence. The scope is
recorded deltas only: unrecorded historical work is not included. If telemetry is
absent, state unavailable and do not invent a row of zeros.

Progress = fresh passing criteria / all criteria, equally weighted. Stale/failed/
unproven criteria do not count, even if a subgoal is marked done. Missing or invalid
gate gives an unknown percentage. All gates, reviews and deployment checks must be
listed before calling 100% a completed task; synthetic examples are not real results.

Example report: `Tokens: unavailable (known 12,000; 2/3 runs); failed attempts:
1; acceptance: 75% (3/4 fresh criteria).` Name the models actually used. Claim cost
or quality improvements only after representative comparable successful runs.
