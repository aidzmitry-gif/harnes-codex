# HRE-TERRA-ERP — portable Terra support and ERP adoption

## Approved outcome and boundaries

2026-10-28: user requested GPT-6.1 Terra support in Harness and ERP and GitHub publication; user delegated the isolation choice. Publish Harness to aidzmitry-gif/harnes-codex and ERP integration to aidzmitry-gif/CMR-ERP_main in separate branches. Do not alter either active dirty checkout, AGENTS.md, active passports, global configuration, production, credentials or business data.

Reuse the existing local HRE-TERRA-001 implementation as a source of scoped changes, not as evidence that the published baseline works. Its patch does not apply to commit 680ac4d and contains Windows-relative paths; port only required Terra behavior. Existing source work remains untouched.

## Metrics and acceptance

- Result: explicit `gpt-6.1-terra` passports validate and dispatch exact model/effort; missing or unsupported effort fails closed; legacy models and authority checks remain unchanged. New read-only visual role is included in install/upgrade/uninstall. ERP receives the verified release only in an isolated checkout. Publication is verified against remote commit IDs.
- Operations: reuse the existing validator, planner, installer and distribution CLI (laziness ladder rung 2). No new router, model API client or scheduler. Record actual commands and failures below; no measured reduction in user operations yet.
- Time and tokens: measure verification segments. No real-inference quality, latency, subscription/API cost or token savings claimed without comparable observed model runs. Earlier private-payload pilot authorization remains separate.
- Safety: original source and ERP AGENTS.md and global config hashes must remain unchanged. Neither active checkout is reset, staged, committed or deployed.

## Impact and rollback

Medium risk: exact model allowlist, read-only role, managed-role ownership and fixed release payload. No API/DB/network surface is introduced in the product. Inspect consumers in validator, planner, installer and uninstall. Revert the task commits to roll back published source; retain installer receipts/backups. No deletion or rollback of other users' work.

## Verification plan (before execution)

Clean baseline has 191 unittest methods. Prechange: configured gate (191 methods, passport, benchmark, bootstrap and architecture). Targeted: validator 26 + orchestrator 22 + distribution 19 = 67 unique methods; installer lifecycle is one separate script. Postchange and release: mandatory configured checks, including installer lifecycle at release. New scenarios will extend existing methods or have a declared new count before execution. Success means all planned checks pass, both task commits are remotely present, and installed ERP files verify against their receipt. A green structural test is not an inference benchmark.

## Primary sources checked

- https://developers.openai.com/api/docs/models/gpt-6.1-terra — explicit model; API efforts none/low/medium/high/xhigh/max; tools require Responses. API settings are not copied into Codex capabilities.
- https://learn.chatgpt.com/docs/models — Codex CLI minimum 0.159.0; model selection remains explicit.
- https://learn.chatgpt.com/docs/model-selection — same-input/same-effort comparisons, regression tests and saved-result verification.
- Current callable Codex host metadata supports Terra low/medium/high/xhigh/max/ultra. Preserve legacy `terra`; do not silently remap models.

## Evidence / status

Orientation complete. Original Harness has 28 tracked modified files; ERP main checkout has 669 dirty entries and concurrent tasks. Isolated Harness worktree created at 680ac4d. Scoped source changes are now implemented; publication is pending. ERP installation remains blocked below.

Prechange attempt 1 used optional Strict and returned 1 solely for the expected new work-item warning; mandatory checks completed. Read the gate exit condition: Strict rejects warnings. Retry uses normal prechange with the documented warning retained, no checks weakened.

Normal prechange PASS: 191/191 unittest methods (25.303s), all configured checks; total 32.981s. One wrapper launch failed before tests because a copied Windows environment dictionary used a mixed-case SYSTEMROOT key; fixed the invocation only. Targeted set remains 67 methods; new model cases extend existing methods. Exact gpt-6.1-sol support is included to enable the documented same-input Terra/Sol comparison without changing defaults.

ERP write blocker: the app refused create_worktree because ERP is not an attached workspace folder. Do not bypass with shell Git or remote mutations. Prepare portable Harness independently; request adding the ERP workspace before its isolated installation/commit. User delegated isolation choice and reconfirmed GitHub push. ERP remote was verified read-only as aidzmitry-gif/CMR-ERP_main.

Targeted model/planner PASS 48/48 (1.258s test runtime). Targeted distribution PASS 19/19 (16.259s), including portable release handling. Installer lifecycle attempt 1 reached uninstall after successful fresh/preview/custom-cap20/legacy upgrade and idempotent retry, then refused a mismatched junction. Root cause: new test code used default ANSI Get-Content for a UTF-8 receipt and reserialized corrupted Cyrillic paths. Fixed the three new JSON reads with explicit UTF8; no product ownership/security check weakened.

Installer lifecycle PASS after that correction (37.973s): fresh five-role install, unmanaged-role refusal, exact legacy four-role upgrade/uninstall, cap20/config-preserving RolesOnly, no-write WhatIf, idempotence, manifest-tampering refusal and transaction rollback. The immediately prior retry result was lost at context rollover; its follow-up process ID was no longer available, so this explicit verification run is the retained evidence. Skill Creator quick validation PASS; its review removed a repository-relative documentation link that would resolve incorrectly from the global skill directory. Existing legacy Luna authority coverage is retained alongside the new exact models. No live inference benchmark was run.

Postchange Strict PASS: 191/191 unittest methods (25.074s), passport, benchmark, bootstrap and role architecture; total 32.786s. `git diff --check` PASS. Review pass 1 checked exact effort/authority contracts, read-only visual actions, manifest allowlists, no-write preview, config preservation, rollback and legacy uninstall. Pass 2 retained the existing validator/planner/installer mechanisms, with no new routing layer or dependencies. README role counts now match the current five-role and legacy four-role cases.

Release manifest validates: `2026.10.28-terra.1`, 18 existing managed core paths, bundle `481a7064924a06d53f4c95738de190f195a34ec60b7361787ab529122419de09`. This is a scoped port onto the published baseline, not publication of the original checkout's unrelated HRE-013/014/015 work. Role installation is a separate managed installer operation, not part of copying the core payload.

Read-only ERP plan completed after correcting the caller to unpack the CLI's tuple return: 2 conflicts (`acceptance_gate.py`, `docs/ENGINEERING_LOOP.md`), 16 create candidates, `canApply=false`, local Harness profile absent. No files or receipts were written. Besides the workspace access blocker, these existing ERP contracts need an explicit compatibility merge/review in an isolated checkout, not forced replacement. Recheck after ERP is attached as a workspace folder and isolation is available; acceptance requires resolving those two conflicts and verifying the new receipt plus ERP-specific tests. No ERP commit/push or live model trial has occurred.

Release Strict PASS: 191/191 unittest methods (24.770s), configured passport/benchmark/bootstrap/architecture checks and installer lifecycle; total 70.416s. Source-side acceptance is verified and ready for publication in `codex/gpt61-terra-harness`; exact remote commit confirmation is reported after push. ERP adoption remains externally blocked, so the combined Harness + ERP outcome is not complete. Token usage and actual inference economy remain unknown; failed attempts and their localized causes are recorded above.
