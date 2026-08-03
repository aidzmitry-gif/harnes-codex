# Контекст проекта «Харнес разработка»

<!-- context-handoff:start -->
## Current handoff

- Updated: 2026-08-04T00:48:04+03:00 (Europe/Minsk)
- Objective: завершить HRE-001 свежим schema-v2 acceptance evidence, чистым strict release и правдивой telemetry, после чего перевести результат на проверку пользователя.
- Verified state: локальная ветка `main`, HEAD `d3ac1db`; рабочее дерево было чистым перед этим snapshot. G01–G06 приняты. Независимый G07 exact re-probe на `29cdb4c` дал PASS: все прежние P1–P3 закрыты; 38 тестов, оба паспорта, benchmark, architecture, installer, diff-check и strict release прошли. G07 остаётся `running` только до свежего acceptance/telemetry closure.
- Decisions and invariants: HRE-001 revision 1 и standing authorization scope `both` подтверждены; один writer на checkout; только локальные файлы и Git, без network/push/deploy/миграций/секретов; токены записывать только фактические, иначе `null`; архивировать цепочку только по отдельной явной команде пользователя; predecessor оставить неархивированным.
- Changed surfaces: `acceptance_gate.py`, `harness_metrics.py`, `goal_runner_validator.py`, `harness_benchmark.py`, их тесты/fixtures, Goal Runner и Context Handoff skills, templates/docs/config/scripts, executable passport и work journal.
- Verification: 2026-08-04 Europe/Minsk — `python goal_runner_validator.py check .harness/work/hre-001.passport.json` PASS, snapshot hash `b7c4dd77bd69712521e74255ce5a55b12f3191be`; `scripts/Invoke-HarnessGate.ps1 -Stage prechange` PASS with 38 tests; independent verifier reported clean strict release at `29cdb4c`.
- Measurement continuity: baseline `legacy-unchecked`; treatment `harness-evidence-v1`; metrics `.harness/metrics/hre-001.jsonl`, schema 1; production token evidence remains unknown, not estimated.
- Open blockers or risks: no code blocker. Existing acceptance evidence must be freshly re-proved after final passport state; path comparison is intentionally case-insensitive for the Windows workspace. Do not claim statistical significance or production token savings from the synthetic 20-pair regression benchmark.
- Next minimal slice: verify this snapshot and passport read-only; then set G07/passport to `awaiting-user-review`, commit, create/check fresh HRE-001 and architecture acceptance evidence, run one clean strict release, append one truthful telemetry event, and confirm clean Git. Acceptance: all criteria fresh/PASS, release PASS, validator PASS, telemetry tokens `null`, no active agents.
- Startup reads: `AGENTS.md`; `.harness/CONTEXT.md`; `.harness/work/hre-001-evidence-efficiency.md`; `.harness/work/hre-001.passport.json`; `.agents/skills/goal-runner/SKILL.md`.
- Active work item: `.harness/work/hre-001-evidence-efficiency.md`
<!-- context-handoff:end -->
