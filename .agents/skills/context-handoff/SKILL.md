---
name: context-handoff
description: Safely transfer active project work from a long or compacted Codex task into a clean successor task, including bounded Goal-chain handoffs approved through `$goal-runner`. Use when the user invokes `$context-handoff`, asks to continue in a clean task without the transcript, when a task has compacted, or when an approved Goal chain crosses a context boundary. Update one canonical project context file, verify every successor, and never fork or copy full chat history.
---

# Context Handoff

Transfer verified state through project files, not through the old transcript.

## Invariants

- Treat task and chat as synonyms; use the user's language and the product term **task** rather than internal thread terminology.
- Never use fork: it copies the source transcript and its context load.
- Never include screenshots, browser ambient state, full logs, tool transcripts, secrets, `.env`, personal data, or speculative conclusions.
- Never create a successor task until the user confirms the prepared title, project, environment, and prompt, except in Goal-chain mode with a recorded standing chain authorization for that exact chain and project.
- Never archive the source task until the successor has opened successfully and the user confirms archiving separately. In Goal-chain mode, leave predecessors unarchived until the user explicitly requests archive of the completed chain.
- Preserve local `AGENTS.md`, project rules, worktree policy, data ownership, and stop conditions.
- Keep the marked handoff snapshot below 900 words and the successor prompt below 250 words.

## Workflow

### 1. Establish the boundary

State the current outcome in one sentence. Stop for direction if the goal, project, data owner, active work item, next slice, or expected behavior is ambiguous. Do not hand off while a destructive operation, migration, deployment, or unresolved approval is active.

An explicit `$context-handoff` invocation authorizes updating the canonical snapshot. If the skill triggered from natural language that did not clearly request a write, show the proposed snapshot and obtain confirmation before editing. Neither form authorizes task creation or archiving unless the active Goal work item contains valid standing chain authorization as defined below.

### 2. Find one canonical context file

Use this precedence:

1. A context or status path explicitly named by local instructions.
2. Existing `.harness/CONTEXT.md`.
3. One clearly designated project status or live-work journal.
4. Otherwise create `.harness/CONTEXT.md`.

Do not create a second competing journal. An active `.harness/work/<id>.md` remains the detailed evidence record; link it from the canonical context instead of copying it.

### 3. Collect only current evidence

Read the narrowest useful set:

- applicable instructions;
- the active work item and canonical context;
- current git status and a diff summary when git exists;
- fresh relevant verification results, rerun safely when local policy requires it;
- read-only Graphify traversal when `graphify-out/graph.json` exists and it materially reduces repository reading.

Before editing the snapshot, follow any local work-item and preflight gate required for project writes. Do not let a Graphify query create feedback, vocabulary, memory, or rebuilt graph artifacts during handoff.

Do not re-read the whole repository or recover the old transcript. Separate verified facts from assumptions. Independently verify any conclusion originally derived from a screenshot; otherwise mark it unknown. Record the command, result, and observation time for verification evidence. Treat inferred or ambiguous Graphify edges as assumptions until independently verified.

### 4. Update the canonical snapshot

Create or replace only the section between these markers, preserving all unrelated content:

```markdown
<!-- context-handoff:start -->
## Current handoff

- Updated: <ISO timestamp and timezone>
- Objective: <one observable outcome>
- Verified state: <facts only>
- Decisions and invariants: <short list>
- Changed surfaces: <paths/components, not pasted diffs>
- Verification: <commands and concise results>
- Open blockers or risks: <none or short list>
- Next minimal slice: <one action and its acceptance check>
- Startup reads: <at most five paths>
- Active work item: <path or none>
<!-- context-handoff:end -->
```

If an existing marked section is malformed or duplicated, stop and show the conflict instead of overwriting uncertain content.

### 5. Prepare the successor

Draft and show:

- a short outcome-oriented title;
- the exact saved project and safe execution facts: project path, checkout or worktree mode, OS/shell, and necessary non-secret runtime facts only;
- a startup prompt of at most 250 words.

The prompt must make the first turn verification-only. Tell the successor to read the canonical context and applicable instructions, avoid reconstructing the old chat or screenshots, verify the recorded state, and report one next minimal slice. In normal mode it waits for user direction. In approved Goal-chain mode the primary orchestrator may send the implementation follow-up after it verifies this acknowledgement.

In normal mode, ask one explicit question: whether to create this clean successor task. Treat `$context-handoff` as authorization to prepare and write the snapshot, not as authorization to create or archive tasks. In Goal-chain mode, show the prepared successor in the progress update but do not pause when the recorded authorization covers it.

### 6. Create without copying history

After normal confirmation, or after validating Goal-chain authorization, use the available Codex task tools:

1. Resolve the saved project rather than inventing an ID.
2. Create a new task with the prepared title and prompt; do not fork.
3. Make the source task quiescent after snapshot capture. Preserve the current local checkout only when continuity depends on uncommitted files and no concurrent writer remains. Use an isolated worktree when the user requested isolation or local project policy requires it.
4. If task creation tools are unavailable, provide `Ctrl+N`, the exact project path, title, and prompt. Do not claim creation succeeded.

### 7. Verify and close

Wait once for a bounded successor status snapshot, up to 60 seconds. Do not poll repeatedly. Success requires the new task to acknowledge the canonical file, objective, verified state, and next minimal slice without starting implementation. If it cannot or times out, keep the source active and repair the snapshot or prompt.

When verification succeeds in normal mode, report the successor link/identifier and ask separately whether to archive the source task. Archive only after that explicit answer. Never delete either task.

In Goal-chain mode, register both task IDs in the parent work item, mark the predecessor `idle-pending-review`, and transfer write ownership to the successor. Continue the approved next slice without another prompt only when the separately validated authorization scope permits bounded continuation. Do not ask to archive the predecessor and do not leave it running.

## Goal-chain mode

Use this mode only when all of the following are recorded in the active parent work item:

- a stable chain ID and unchanged parent outcome;
- the exact project and checkout/worktree policy;
- the user's approval of the Goal passport;
- `standing chain authorization: approved` and `Standing authorization scope: successor creation | bounded continuation | both`;
- an `Approved passport revision` equal to the current `Plan revision`, plus exact approval provenance;
- a validator-readable executable plan snapshot linked from the work item, last validation/hash, and the current verified boundary;
- deferred archive policy requiring a final explicit chain command;
- the current verified subgoal and next minimal slice with its acceptance check;
- project root, data owner, risk class, external-side-effect boundary, and checkout/worktree policy.

The authorization is invalid if any required field is absent or ambiguous; the approved and current plan revisions differ; approval provenance cannot be traced; or the project, parent outcome, data owner, risk class, external side effect, acceptance, or checkout ownership changes. Fall back to the normal confirmation workflow.

Number successors `<CHAIN> · HNN · <next result>`. Create one automatically only when scope is `successor creation` or `both`. Keep the source quiescent after snapshot capture and verify the successor once. Let the primary orchestrator send the next implementation instruction automatically only when scope is `bounded continuation` or `both`; with creation-only scope, stop after verification and ask. Revalidate the complete authorization contract at both boundaries. Never archive a Goal chain during handoff. After the parent result passes its acceptance checks and the user explicitly says to archive that chain ID, archive registered tasks and never delete them.

For a Goal-chain handoff, the marked snapshot may carry only measurement continuity: treatment ID, metrics path/schema, the last validated executable plan snapshot and hash (or equivalent), and the current verified boundary. The successor must run `python goal_runner_validator.py check <snapshot>` before continuing. Do not copy telemetry rows, chat/transcript, raw logs, or inferred token counts; runtime token values remain actual values or `null`.

## Completion report

Report at least these four items: canonical context path, successor task, verification result, and source archive status. Include limitations or residual risks when local handoff rules require them.
