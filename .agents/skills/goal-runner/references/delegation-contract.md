# Delegation contract reference

## Task packet

```text
Chain/subgoal:
Role and model intent:
Observable outcome:
Prepared inputs, user action, expected visible result, evidence location:
Scope and owned paths/worktree:
Commit authority: none | isolated-worktree checkpoint
First sufficient laziness-ladder rung:
Why lower rungs fail:
Explicit exclusions:
Inputs/startup reads (max 5):
Dependencies and verified assumptions:
Required evidence:
Acceptance command or review criterion:
Stop conditions:
Child-agent quota and allowed roles:
Report limit: 500 words plus paths/commands
```

Do not delegate an ambiguous outcome or paste the parent transcript.

## Contract acknowledgement for writes or high risk

The first turn must be read-only:

```text
UNDERSTANDING
Outcome I will deliver:
Paths/worktree I own:
What I will not change:
Evidence that will prove completion:
Dependencies I accept:
Open ambiguity or blocker:
```

Compare outcome, ownership, exclusions, dependencies, and proof. Send an implementation follow-up only after all five match. Confidence is not a substitute for this comparison.

## Completion report

```text
RESULT
Outcome:
Claims and source paths:
Changed files:
Commit hash (only when explicitly authorized):
Ladder rung, simplifications, retained exceptions, and ponytail triggers:
Commands/checks and concise results:
Unknowns or assumptions:
Residual risks:
Confidence: high | medium | low
Recommended next action:
```

Reject reports that omit evidence, hide failing checks, exceed ownership, or claim completion from confidence alone. For high risk, assign a different read-only verifier and require it to reproduce acceptance evidence.

## Communication

- Report upward to the assigned lead or primary orchestrator.
- Return a blocker once with its affected scope and observable resume condition; do not ask the user directly or repeat a failed access attempt without changed prerequisites. The primary continues independent authorized work and batches decisions.
- Message peers only for a named dependency and copy the distilled conclusion upward.
- Keep raw logs in the agent task or an approved artifact; return only the relevant excerpt and location.
- A child may spawn descendants only when its packet grants a positive slot quota and names allowed roles. Default quota is zero.
- A worker must not stage or commit unless its packet grants isolated-worktree checkpoint authority. It never pushes.
