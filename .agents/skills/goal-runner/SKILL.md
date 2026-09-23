---
name: goal-runner
description: Execute an approved large Goal as a dependency-aware graph. Use for `$goal-runner`, explicit goal decomposition, parallel goal waves, or master orchestration; ordinary coding tasks do not need this skill.
---

# Goal Runner

Run one large outcome through a verified DAG of subgoals while keeping the main task focused on contracts, decisions, and evidence.

## Preserve authority and safety

- Treat invoking `$goal-runner <objective>` as authority to inspect and prepare a plan, not to deploy, migrate, publish, delete, handle secrets, or broaden sandbox access.
- Before implementation or spawning workers, show the Goal passport and obtain one explicit approval of the decomposition and bounded orchestration policy.
- Let that approval authorize only the listed Goal chain: planned subagents, child tasks, clean successor tasks, and assigned local worktrees. Keep normal approval and stop conditions.
- Once bounded continuation is approved, complete every listed safe subgoal without asking the user to say "continue" between implementation, tests, corrections, and review. Reconfirm only a material scope/risk/authority change or a genuine stop condition; approval does not override sandbox permissions.
- Never fork a task or copy its transcript. Never archive Goal-chain tasks until the user reviews the parent result and explicitly requests archive of the chain ID.
- Keep one writer per checkout or worktree. If isolation cannot be proved, serialize writes.

## 1. Establish the parent contract

1. Read applicable instructions, canonical project context, active work item, git state, configured checks, and only the files needed to locate the Goal boundary.
2. Use an existing read-only Graphify graph when it materially reduces repository reading. Do not rebuild it merely to start a Goal.
   Start from the canonical work item and current context, then at most five relevant source pointers; expand only for a concrete unanswered question. Check snapshot branch/revision/evidence freshness against the checkout. If context is stale, recover from the current passport and files, not the transcript. Graphify supplies navigation, never approval or a fabricated project goal.
3. Create a stable chain ID such as `SEO-001` and one work item at `.harness/work/<goal-id>.md`. Do not create a competing project journal.
4. Record the observable parent outcome, exclusions, invariants, acceptance checks, risk, rollback, and approval boundaries.
   Define one user-visible acceptance scenario: safe prepared inputs, the action to perform, the expected observable output, and where fresh evidence will be recorded. For UI/export work, include a filled example and inspect the actual view/download, not just an HTTP status or successful build. Reuse the existing acceptance gate; distinguish local verification, deployment, and user acceptance.
5. Read [goal-state.md](references/goal-state.md) when creating or resuming Goal state.
6. Read [laziness-ladder.md](references/laziness-ladder.md) before the first implementation packet and every final code review.
7. Create one owner-maintained executable plan snapshot at `.harness/work/<chain>.passport.json`, link it from the canonical work item, and run `python goal_runner_validator.py check <snapshot>`. The Markdown work item remains the decision journal; the snapshot is the runnable projection, not a competing source of truth.

## 2. Decompose before execution

- Choose the smallest sufficient number of measurable subgoals. A large Goal may require 3, 12, 20, or more; do not impose a cosmetic count.
- Give each subgoal a stable ID, observable result, dependencies, subsystem, risk, acceptance check, execution mode, and proposed model.
- Before any measured execution, assign explicit bounded baseline and treatment IDs in the Goal state. Do not infer them from model names or fill them in after a run.
- Build a DAG. Put only dependency-free `ready` subgoals into the next parallel wave.
- Keep IDs stable. Append discoveries with new IDs; mark removed goals `skipped` with a reason.
- Group a long list into phases without hiding individual results.

Before execution, show the parent outcome and chain ID; total subgoals and phases; every subgoal result and acceptance check; dependency waves; planned roles, models, worktree ownership, and handoffs; and actions that still require separate approval. Wait for one explicit approval. Revise and show the delta if the user changes the plan.

## 3. Allocate a bounded global pool

- Read the callable concurrency limit. Treat configured capacity as a cap, not a target. This harness requests up to 12 subagents, excluding the primary orchestrator.
- Degrade to smaller waves when the runtime exposes fewer slots. Never claim agents are running unless task tools confirm it.
- Allocate one global pool across active subgoals; do not grant every subgoal an unlimited pool.
- Allow at most two delegation levels below the primary orchestrator. A read-only child-goal lead may spawn only read-only descendants when its packet grants a slot quota and names allowed roles; the primary dispatches all workspace-write workers.
- Prefer hub-and-spoke communication. Allow peer messages only for a named dependency.
- Keep canonical Goal state single-writer: only the primary orchestrator updates the parent work item and `.harness/CONTEXT.md`.
- Size the pool to independent work, not capacity: a small slice may need only the primary; add read-only exploration or verification when it has a concrete question. Keep support packets bounded rather than forwarding the whole conversation.

Use separate regular tasks only for distinct long-lived outcomes or context boundaries. Use subagent tasks for bounded exploration, implementation, verification, tests, or log analysis. Name visible tasks `<CHAIN> · GNN · <result>`.

## 4. Route roles, models, and environments

- Use `harness_goal_explorer` for read-heavy mapping.
- Use `harness_goal_worker` for one approved minimal implementation slice.
- Use `harness_goal_verifier` for independent acceptance and safety review.
- Use `harness_goal_lead` as a read-only coordinator when a child goal needs its own small exploration or verification tree.
- Source profile for new bounded implementation, tests, documentation and clear exploration: `gpt-6-luna` / `xhigh` to preserve the prior effort during migration. A clear low-risk slice with a targeted oracle may use Luna `low` or `medium` only when that exact plan is approved and acceptance remains intact. Use `gpt-6-sol` / `high` for everyday coding judgment, integration and child-goal coordination; use `gpt-6-astra` / `xhigh` for ambiguous contracts, security, permissions, migrations, complex debugging and final high-risk review. A narrow write packet may return to Luna after the contract is fixed.
- These are routing hypotheses, not measured quality or savings. Compare the same scoped inputs, fresh acceptance and observed usage before claiming a faster/cheaper profile. Before dispatch, verify that the callable runtime exposes the exact model/effort: this Goal validator permits `low` through `max` for GPT-6 Sol/Luna, not API-only `none` or unsupported `ultra`. Put both `model` and `reasoningEffort` in new passports; the planner forwards them. Legacy `terra`/`sol`/`gpt-5.6-luna` passports stay unchanged until an approved revision.
- Check the selected role's actual fixed model. If an installed role still pins Terra/Sol, do not claim to override it: use a model-selectable default agent with the same bounded role contract and explicit model/effort, only where delegation is authorized. Use a short packet (`fork_turns=none`), never a full-history fork with overrides. For `execution=primary`, record the actual current model; a plan cannot switch its own running model.
- If the selected model is unavailable, hold the affected slice and request a fallback choice; do not silently substitute a cheaper model on high-risk work. Existing agents/global configuration are not rewritten by this skill.
- After an unsuccessful implementation verification, narrow the contract once; if the same cause persists or safety is involved, ask Astra to diagnose before another write. Preserve the no-progress stop condition and all permission gates; switching models alone does not unlock a retry.

Parallelize read-only work within the pool. For write work, assign file/component ownership, use separate git worktrees for independent goals, never let two agents write one checkout concurrently, serialize integration through the primary orchestrator, and do not create a worktree from an ambiguous or dirty base.

## 5. Verify delegated understanding

Read [delegation-contract.md](references/delegation-contract.md) before the first delegation batch.

- Give every agent a bounded packet: outcome, scope, exclusions, inputs, evidence, acceptance, stop conditions, ownership, role/model, child quota, the first sufficient laziness-ladder rung, and why lower rungs fail.
- For writing or high risk, make the first agent turn orientation-only. Require a contract acknowledgement and no edits. Compare its restated outcome, boundaries, and proof before sending an implementation follow-up.
- Immediately before any worker write, validate the current executable plan snapshot with `python goal_runner_validator.py check <snapshot>`. Revalidate after every plan revision, authorization change, or agent-registry change; do not dispatch from an invalid snapshot.
- Correct an acknowledgement that changes the outcome, expands scope, misses an invariant, or cannot name the acceptance check.
- Require concise reports with claims, paths, commands, results, unknowns, changed files, risk, and confidence. Do not import raw transcripts or full logs into the parent context.
- Treat tests, file evidence, and independent review as stronger than agent confidence.

## 6. Execute waves

For each wave:

1. Recheck dependencies and writer isolation.
2. Apply the laziness ladder and stop at the first rung that fully meets the contract; record rejected lower rungs.
3. Spawn only agents that fit the global pool and assigned worktrees.
4. Wait for the bounded batch and collect reports.
5. Run the correctness review and verify critical claims locally or with an independent verifier.
6. Run a separate simplify review against the laziness ladder without weakening the safety floor.
7. Accept, correct, retry once with a narrower contract, or mark blocked.
8. Update status, ladder decision, simplifications, exceptions, evidence, registries, decisions, and the next wave in the parent work item.
9. At meaningful run or accepted-subgoal checkpoints only, use `python harness_metrics.py record --file <metrics.jsonl> --from <event.json>`. Include `failedAttempts` (integer or `null`) for schema 2; legacy schema 1 remains readable. Record one non-overlapping delta per unique `runId`, with `chainId`, actual model/effort and observed tokens (both `null` if unavailable). Do not sum cumulative usage snapshots, count child usage again inside the parent, or infer failures from checksFailed/reworkCount. Never store transcripts/free text. See [task-metrics.md](references/task-metrics.md) for the event contract and required task report.
10. Treat `python harness_benchmark.py --fixture tests/fixtures/hre-001-benchmark.json` as a deterministic regression oracle for common-ground-truth quality semantics. It does not prove real-world token savings or statistical significance.
11. Acceptance evidence is fresh only for the current relevant repository state; after a relevant change, run `acceptance_gate.py prove` again before accepting manual evidence.
12. Before retrying the same subgoal, run `python goal_progress.py check <passport> <subgoal> <strategy>` and record a permitted attempt with `record`. `NO_PROGRESS` is a stop condition: change the bounded strategy, repository state, or structured fresh evidence before retrying; do not evade it by rewriting narrative evidence.
13. Run targeted checks before fast checks; run full checks according to risk.

### Control DAG and Graphify are separate

- The executable passport is the control DAG: it authorizes dependency transitions, writer ownership, and the no-progress gate.
- A local Graphify knowledge graph is a read-only discovery aid. It can reduce repository reading, but it neither changes passport status nor unlocks a subgoal.
- Graphify output is not acceptance evidence by itself. A transition requires the passport's current, fresh acceptance evidence; Graphify may be cited only as navigation to the files or checks that produce that evidence.

### Parent Goal Play/resume control

- Keep one native Goal in the primary task. Use subagent tasks for bounded work and separate regular tasks only for distinct long-lived outcomes or safe context boundaries; do not create a native Goal for every short subgoal.
- On primary Goal start/resume and after every accepted result or plan revision, run `python goal_orchestrator.py plan <passport> --parent-state running`. Use `paused` or `blocked` when that is the actual parent state. The planner validates the current passport and returns actions; it never presses UI controls, starts tasks, changes status, or writes files.
- Interpret `launch` as permission to dispatch only the listed ready slice after one more current-passport validation. Interpret `wait` as a prohibition on duplicate work and `verify` as a requirement to reproduce evidence before marking the subgoal done. A local `hold` (`subgoal_blocked`, `agent_blocked`, `dependency_blocked`, `worktree_busy`) stops that slice and affected dependencies, not independently authorized launches. Parent pause/block, a non-executable chain, or missing continuation authority remain global prohibitions. An active child under a paused/blocked parent should reach a safe checkpoint and stop; do not claim the UI pause cascaded automatically. Recheck actual writer isolation before dispatch; different goal IDs do not prove different worktrees.
- Treat `complete` as a scheduling signal, not parent acceptance. The correctness review, simplify review, integration checks, fresh evidence, and parent acceptance in section 9 remain mandatory.
- Return child blockers and user questions to the primary task. Batch decisions there so the user normally interacts with one Goal task rather than supervising each child.

### Update impact radar

Only when reviewing OpenAI/Codex updates or operating the update watcher, read [update-radar.md](references/update-radar.md). Ordinary Goal execution does not load this reference.

Do not reconstruct the parent plan on every cycle. Re-read durable state and only the evidence needed for the next wave.

### Git checkpoints and change journal

- When the project is a git repository and the approved passport enables commits, create one atomic checkpoint only after a subgoal passes acceptance. Use `<CHAIN>/<GNN>: <observable result>` and record the hash beside the evidence.
- Let the primary orchestrator create integration commits in a clean integration checkout/worktree. Before writes, record the baseline status/diff; abort a checkpoint when user and agent changes overlap in one file or ownership cannot be separated. A worker may commit only in an explicitly assigned clean worktree when its packet grants checkpoint authority; otherwise it reports the diff upward. Agents never push automatically.
- Never commit a broken intermediate state, unrelated user changes, secrets, generated noise, or every touched file via broad staging. Review the exact staged paths and tests first.
- Before every commit, review `git diff --cached` against the recorded baseline and unstage anything outside the accepted subgoal.
- Do not treat git history as the decision journal. Keep rationale, plan revisions, checks, and rollback evidence in the parent work item. In a non-git project, record that commits are unavailable and preserve the same durable journal.

## 7. Replan visibly

Report a plan revision before executing new scope:

```text
Plan revision: 2
Previous subgoals: 12
Added: G13 — preserve legacy URL compatibility
Reason: verified dependency discovered in <path/test>
Impact: wave 4 gains one prerequisite; parent outcome unchanged
```

Never silently expand the parent outcome. Stop for approval when outcome, data owner, external side effect, risk class, or acceptance changes materially.

## 8. Hand off without stopping the chain

Invoke `$context-handoff` in approved Goal-chain mode only when the current slice is verified, durable state is current, no destructive/external operation is active, and the predecessor will become idle.

```text
safe_boundary AND (
  subsystem_changed OR
  visible_context_remaining <= 45% OR
  compaction_count >= 2
)
```

- Use an exact context percentage only when exposed by the runtime.
- Treat the third compaction as an emergency maximum.
- Number successors `<CHAIN> · HNN · <next result>` and register every task ID.
- Before creating a successor, revalidate every required Goal-state field, require `Approved passport revision` to equal the current `Plan revision`, verify `Approval provenance`, and require `Standing authorization scope` to be `successor creation` or `both`.
- Before creating a successor, carry only the treatment ID, metrics path/schema, last validated plan snapshot and hash (or equivalent), and current verified boundary. Revalidate that snapshot in the successor; never copy telemetry rows, transcript, chat history, or fabricate token counts.
- After successor acknowledgement, send an implementation follow-up automatically only when the same authorization still validates and `Standing authorization scope` is `bounded continuation` or `both`. Creation-only authority must stop after verification and request confirmation.
- Otherwise use normal confirmation.
- Leave predecessors idle and unarchived. Never keep two chain tasks writing the same checkout.

## 9. Complete and archive

Complete the parent Goal only when required subgoals are `done` or accepted as `skipped`, integration checks pass, correctness and simplify reviews pass, and parent acceptance succeeds. Report results, evidence, laziness-ladder decisions, retained exceptions, deviations, risks, and the task chain; wait for user review. Archive registered tasks only after an explicit command such as `Archive Goal chain SEO-001`; archive, never delete.

At meaningful status updates and final handoff, include one short line: tokens (or unavailable with known coverage), recorded failed attempts, and fresh acceptance percentage with numerator/denominator. Run `python harness_metrics.py task --file <metrics.jsonl> --chain <CHAIN> --work-item <acceptance-id>` from the target project root. Missing telemetry/gate means unknown, never zero/100%. A percentage describes the declared acceptance criteria only, not elapsed time or proof of deployment.

## Stop conditions

Stop when permissions, ownership, behavior, isolation, destructive impact, or parent acceptance is ambiguous; a high-risk action lacks approval; or two independent diagnostic attempts fail without localizing the cause.
