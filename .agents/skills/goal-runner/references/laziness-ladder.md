# Laziness ladder

Use the first sufficient rung before writing code. Record why lower rungs do not satisfy the approved outcome.

1. **Do nothing (YAGNI).** Skip speculative behavior and say why in one line.
2. **Standard library or language feature.** Reuse it instead of custom machinery.
3. **Native platform primitive.** Prefer browser/CSS, database constraints/triggers/RLS, framework primitives, or the platform's built-in capability.
4. **Existing project dependency.** Reuse it; do not add a dependency to save a few lines.
5. **One direct expression or line.** Keep it local when that remains readable and testable.
6. **Minimum working code.** Add only the smallest implementation that proves the contract.

Prefer deletion over addition, fewer files, and inlining a one-implementation interface until a second implementation exists. Do not add speculative factories, adapters, configuration, extension points, or infrastructure.

## Safety floor

Never simplify away:

- validation at trust boundaries;
- error handling that prevents data or money loss;
- security, authorization, privacy, auditability, and required accessibility;
- concurrency or transaction correctness;
- explicitly requested behavior and acceptance evidence;
- a documented shared platform kernel already justified by multiple real consumers.

Mark an intentional bounded simplification with the language-appropriate `ponytail:` comment only when the ceiling is real and useful. Name both the measurable trigger and upgrade path, for example: `# ponytail: O(n^2) scan; add an index when rows > 500`. Do not use the marker for missing correctness, debt without a trigger, or an excuse to skip acceptance.

## Two-pass code review

Run the passes in this order:

1. **Correctness pass:** verify scope, behavior, errors/defaults, compatibility, trust boundaries, data/security, concurrency, tests, rollback, and evidence. Reject correctness defects before simplifying.
2. **Simplify pass:** apply the ladder again to every added abstraction, dependency, file, branch, configuration option, and comment. Remove or inline anything whose lower rung satisfies the same contract. Preserve the safety floor.

Record the chosen rung, rejected lower rungs, simplifications made, retained exceptions, and any `ponytail:` trigger in the subgoal evidence.
