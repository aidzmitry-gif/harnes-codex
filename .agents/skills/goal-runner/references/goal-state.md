# Goal state reference

Use one parent work item as the durable source of truth. Keep `.harness/CONTEXT.md` as the current handoff snapshot, not a second plan.

## Required state

```markdown
## Goal runner state

- Chain ID: SEO-001
- Project root:
- Data owner:
- Risk class: low | medium | high
- External-side-effect boundary:
- Parent outcome:
- Status: planning | approved | running | verifying | awaiting-user-review | complete | blocked
- Plan revision: 1
- Approved passport revision:
- Approval provenance: task ID + user message/time
- Primary task ID:
- Current task ID:
- Checkout/worktree policy:
- Commit policy: primary-only | isolated-worker-allowed | no-commit
- Integration branch/worktree:
- Last accepted commit:
- Current laziness-ladder rung:
- Rejected lower rungs:
- Retained exceptions / ponytail triggers:
- Current verified subgoal:
- Next minimal slice and acceptance check:
- Executable plan snapshot: `.harness/work/<chain>.passport.json` (owner-maintained, validator-readable)
- Last validated plan snapshot/hash:
- Measurement treatment IDs: baseline `<id>` | treatment `<id>` (assigned before measured execution)
- Metrics path/schema: `.harness/metrics/<chain>.jsonl` / schema 1
- Global agent cap: 12
- Active agent count: 0
- Delegation depth cap: 2
- Compaction count: 0
- Context threshold: 45% when visible
- Standing chain authorization: absent | approved
- Standing authorization scope: successor creation | bounded continuation | both
- Archive policy: final-explicit-command

## Subgoals

| ID | Observable result | Depends on | Wave | Subsystem | Risk | Execution | Model | Status | Acceptance/evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G01 | | none | 1 | | low | primary/subagent/task | terra/sol | planned | |

## Agent registry

| Agent/task | Parent | Subgoal | Role | Model/effort | Worktree/files | Status | Report/evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Task chain

| Seq | Task ID | Title | Purpose | Status | Verified successor | Archive status |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | | SEO-001 · 01 · Plan | parent | active | n/a | keep |

## Decisions and plan revisions

| Revision/time | Evidence | Decision | DAG impact |
| --- | --- | --- | --- |
```

## State rules

- Let only the primary orchestrator edit these sections.
- Use stable subgoal IDs; never renumber completed work.
- Record concise evidence and paths, not full logs or transcripts.
- A subgoal becomes `done` only after its acceptance check passes.
- A task becomes `idle-pending-review` after a verified successor takes ownership.
- Record task IDs at creation time so final archival can address the whole chain.
- Recalculate ready waves after every accepted result or plan revision.
- Standing chain authorization is invalid unless project root, data owner, risk class, external-side-effect boundary, approved passport revision, approval provenance, checkout/worktree policy, current verified subgoal, and next minimal slice with acceptance are all recorded.
- A commit is a checkpoint, not the decision journal. Record its hash beside the accepted subgoal evidence and never use it to replace rationale or acceptance results.
- Before any worker writes and after every plan, authorization, or agent-registry change, update the one executable plan snapshot linked from this work item and run `python goal_runner_validator.py check <snapshot>`.
- Assign bounded baseline and treatment IDs before a measured run. Record telemetry only at meaningful run or accepted-subgoal checkpoints with `python harness_metrics.py record`; model token counts are observed runtime values or both `null`, never estimates. Keep identifiers bounded and never put transcript or free text into telemetry.
- Run `python harness_metrics.py compare --file <metrics.jsonl> --baseline <id> --treatment <id>` only when valid pairs exist. Deterministic benchmark results are regression evidence, not a claim of statistically significant or real-world token savings.
