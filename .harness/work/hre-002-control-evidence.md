# Work item: HRE-002 — Evidence-bound control flow

## Цель

- Проблема: Goal Runner проверяет структуру DAG, но статус `done`/`skipped` сам по себе разблокирует потомка; повторная попытка может не отличаться от предыдущей наблюдаемым состоянием.
- Ожидаемый исход: зависимость открывается только свежим локально проверяемым evidence, а повтор с тем же состоянием, evidence и стратегией останавливается как `no_progress`.
- Не входит: LangGraph/внешние сервисы, LLM-as-judge, сеть, push, deploy, миграции, секреты, изменение пользовательского `AGENTS.md`, обещания экономии токенов.

## Контракт и инварианты

- `unlockEvidence` остаётся обратносуместимым: старые паспорта v1 действительны; новый контракт используется только там, где он явно указан.
- Freshness проверяется на текущем repository fingerprint; проверка не запускает произвольные acceptance commands и не читает sensitive files.
- `skipped` не открывает evidence-bound ребро без явной причины, записанной в паспорте.
- `no_progress` определяется только по ограниченным структурированным полям: chain/subgoal, strategy ID, repository fingerprint и evidence fingerprint. Он не сохраняет transcript, секреты или свободный текст.
- Единственный narrative journal — этот work item; машинное состояние попыток остаётся в executable passport.
- Один writer на worktree; `AGENTS.md` основного checkout принадлежит пользователю и не входит в ownership этой цепочки.

## Карта воздействия

- Компоненты: `acceptance_gate.py` (fresh evidence helper), `goal_runner_validator.py` (schema и pure validation), новый минимальный `goal_progress.py` (структурированный no-progress CLI), их unit tests, Goal Runner docs и example passport.
- Потребители: primary orchestrator, worker, read-only verifier и проекты, использующие Goal Runner.
- Данные: passport JSON и acceptance JSON; только bounded IDs, hashes и статусы.
- Безопасность: без запуска command criteria из validator/progress gate; без чтения `.env`/credentials; нет сетевого доступа.
- Откат: локальные атомарные checkpoints в изолированных worktree; revert конкретного commit. Push запрещён.

## Goal runner state

- Chain ID: HRE-002
- Project root: `D:\6 Проекты\Харнес разработка`
- Data owner: пользователь — владелец workspace
- Risk class: medium
- External-side-effect boundary: local-only; no network, push, deploy, migration, deletion, or secrets
- Parent outcome: evidence-bound DAG transitions and a local no-progress stop condition
- Status: approved
- Plan revision: 2
- Approved passport revision: 2
- Approval provenance: user message `Подтверждаю HRE-002 revision 1; AGENTS.md оставить моим baseline и не трогать.`; 2026-08-07 Europe/Minsk. Revision 2 is a bounded corrective slice after independent G04 findings; parent outcome, data owner, risk and external-effect boundary are unchanged.
- Checkout/worktree policy: clean integration worktree; one writer per isolated worker worktree; primary serializes integration
- Commit policy: isolated-worker checkpoints after acceptance; no push
- Current laziness-ladder rung: 2 — Python stdlib and existing acceptance fingerprint helper
- Rejected lower rungs: YAGNI fails because evidence-bound dependencies and no-progress were explicitly approved; direct documentation cannot mechanically reject an unsafe transition
- Current verified subgoal: G02 — revision-2 targeted tests cover and close the four G04 findings
- Next minimal slice and acceptance check: G04 retry independently reproduces the former defects and completes correctness then simplify review
- Executable plan snapshot: `.harness/work/hre-002.passport.json`
- Measurement treatment IDs: baseline `status-only-v1` | treatment `evidence-progress-v1`
- Metrics path/schema: `.harness/metrics/hre-002.jsonl` / schema 1
- Global agent cap: 2; delegation depth: 1; active agents: 0
- Standing chain authorization: approved; scope: bounded continuation
- Archive policy: final explicit command only

## Подцели

| ID | Результат | Depends on | Wave | Ownership | Risk | Execution/model | Status | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | Чистый integration worktree и prechange evidence без затрагивания пользовательского `AGENTS.md` | none | 1 | primary / environment | low | primary / sol | done | clean worktree at `1246c59`; prechange PASS |
| G01 | Optional `unlockEvidence` проверяет stored fresh evidence без запуска команд; stale/missing evidence и необоснованный `skipped` не открывают потомка; v1 compatibility сохранена | P0 | 2 | `acceptance_gate.py`, `goal_runner_validator.py`, tests, fixture/template | medium | worker / terra | done | targeted tests + compatibility suite |
| G02 | `goal_progress.py` распознаёт одинаковую попытку как `no_progress`; новая strategy/evidence/fingerprint допускает следующую попытку; passport хранит только bounded state | G01 | 3 | acceptance/progress/validator и их tests | medium | primary / sol | done | 46 targeted tests close G04 findings; fresh independent review remains G04 |
| G03 | Goal Runner docs и example passport различают control DAG и Graphify knowledge graph; Graphify без свежего покрытия не является acceptance evidence | G01,G02 | 4 | skill docs, README, architecture test | low | primary / sol | done | architecture test + diff review |
| G04 | Независимый read-only verifier воспроизводит негативные сценарии и выполняет correctness затем simplify review | G01,G02,G03 | 5 | read-only integration tree | medium | verifier / sol | running | fresh reproduced checks and report after G02 correction |
| G05 | Fresh HRE-002 acceptance, full suite и strict release подтверждают интегрированный результат | G04 | 6 | primary / acceptance and journal | medium | primary / sol | planned | all criteria fresh PASS; strict release PASS |

## Agent registry

| Agent | Subgoal | Role/model | Worktree | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| `hre002-g01-worker` | G01 | worker / terra-medium | `.worktrees/hre-002-g01` | done | Orientation acknowledgement matched; integration re-ran 32 focused tests, validator and diff check. |
| `hre002-g02-worker` | G02 | worker / terra-medium | `.worktrees/hre-002-g02` | interrupted | Orientation acknowledgement matched; the task ended before a report, so its uncommitted artifact is input to independent review only. |
| `hre002-g02-recovery` | G02 | worker / terra-medium | `.worktrees/hre-002-g02` | done | Ten focused tests and diff check passed; primary independently reproduced the results before integration. |
| `hre002-g04-verifier` | G04 | verifier / sol-high | read-only integration tree | done/reject | Found three correctness defects and one validator coverage gap; no source files modified. |
| `hre002-g04-retry-verifier` | G04 | verifier / sol-high | read-only integration tree | done/reject | Closed four former findings and isolated the float schema-version type defect. |
| `hre002-g04-final-verifier` | G04 | verifier / sol-high | read-only integration tree | active | Final short verifier run after the schema-version type correction. |

## План проверок

1. `python -m unittest tests.test_acceptance_gate tests.test_goal_runner_validator -v` для G01.
2. `python -m unittest tests.test_goal_progress -v` и `python goal_runner_validator.py check .harness/work/hre-002.passport.json` для G02.
3. `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Test-GoalRunnerArchitecture.ps1` для G03.
4. Полный `python -m unittest discover -s tests -v`, затем `scripts/Invoke-HarnessGate.ps1 -Stage release -Strict` для G05.

## Журнал доказательств

| Время | Проверка | Результат | Вывод |
| --- | --- | --- | --- |
| 2026-08-07 | P0: clean `codex/hre-002-control-evidence` worktree from `1246c59`; `Invoke-HarnessGate.ps1 -Stage prechange` | PASS; 38 tests | User-owned `AGENTS.md` remains only in the main checkout and is untouched. |
| 2026-08-07 | G01 orientation acknowledgement | PASS | Worker accepted ownership and negative-evidence contract; implementation may begin only from the validated passport. |
| 2026-08-07 | G01 integration review | PASS | 32 focused tests, current HRE-002 passport validator and diff check passed; stored evidence path does not execute command criteria. |
| 2026-08-07 | G02 orientation acknowledgement | PASS | Worker accepted the no-progress contract; implementation may begin only from the validated passport. |
| 2026-08-07 | G02 independent artifact review | NOT ACCEPTED | Seven focused tests passed, but raw free-text evidence was hashed and whole-passport validation was absent before state write; recovery is required. |
| 2026-08-07 | G02 recovery orientation | PASS | Bounded ownership, privacy correction, fail-closed write validation, attempt limit and negative tests were acknowledged. |
| 2026-08-07 | G02 integration review | PASS | 10 focused tests, passport validator and diff check passed. The signature uses only bounded IDs, status and fingerprints; text changes alone repeat as `NO_PROGRESS`. |
| 2026-08-07 | G03 architecture review | PASS | Architecture script asserts the no-progress CLI and explicit control-DAG/Graphify boundary; the executable passport remains the only transition authority. |
| 2026-08-07 | G04 independent verifier | REJECT | Self-record changed the next repository fingerprint; `passes` truthiness accepted non-bool values; attempt limit allowed 257th write; shared validator ignored `goalProgress`. Revision 2 corrects these defects without expanding the parent outcome. |
| 2026-08-07 | G02 revision-2 correction | PASS (targeted) | 46 focused tests cover self-state exclusion while retaining other passport changes, strict boolean `passes`, exact 256 boundary and shared `goalProgress` schema validation. |
| 2026-08-07 | G04 retry verifier | REJECT | Four prior findings closed, but `goalProgress.schemaVersion: 1.0` was accepted as integer 1. Corrected with an explicit integer check and a regression test; final verifier remains required. |
