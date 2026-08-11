# Work item: HRE-003 — Parent Goal autopilot and update impact radar

## Цель

- Проблема: основной чат хранит проверяемый Goal passport, но не имеет одного детерминированного ответа «какие малые Goal сейчас можно запускать, проверять или удерживать». Обновления Codex/GPT оцениваются вручную и могут смешивать реальные изменения платформы с незначительным шумом.
- Ожидаемый исход: основной чат получает локальный read-only план следующего действия по Goal и структурированный фильтр обновлений, который показывает только изменения с доказанным влиянием на Harness.
- Наблюдаемый критерий успеха: одна локальная команда на валидном passport возвращает bounded JSON с безопасными действиями `launch`, `wait`, `verify`, `hold` или `complete`; вторая команда отделяет значимые официальные обновления от `evaluate`/`ignore` и сохраняет факты отдельно от выводов и допущений.
- Не входит: изменение пользовательского `AGENTS.md`, скрытое управление UI-кнопкой Play, создание отдельной native `/goal` для каждого короткого субагента, автоматический network fetch, выполнение команд из changelog, API-миграция, глобальное обновление Codex/Graphify, push, deploy, публикация, удаление, секреты.

## Подтверждённые наблюдения

- Текущий Harness уже валидирует DAG, ownership, evidence freshness и no-progress, но отдельного next-action planner и update impact classifier в репозитории нет.
- Текущие роли Harness уже используют `gpt-5.6-terra` для explorer/worker и `gpt-5.6-sol` для lead/verifier.
- Локальный пакет приложения расположен в `OpenAI.Codex_26.803.10989.0`; прямой `codex --version` в текущем host возвращает `Access is denied`, поэтому точная CLI-версия остаётся неизвестной.
- Официальный changelog на 2026-08-11 подтверждает стабильный multi-agent V2, улучшенное возобновление Goal, Agent Plugins, защиту секретов и Windows-процессов: https://learn.chatgpt.com/docs/changelog
- Официальная model guidance подтверждает маршрутизацию Sol/Terra/Luna, programmatic tool calling, persisted reasoning и необходимость сравнивать конфигурации на representative tasks: https://developers.openai.com/api/docs/guides/latest-model
- Graphify query нашёл существующие точки интеграции в Goal Runner, validator, acceptance gate, metrics и installer. Graphify является навигацией, а не acceptance evidence.

## Вывод и гипотеза

- Вывод: native возможности Codex следует использовать через существующие task/subagent tools, а Passport должен оставаться единственным control DAG.
- Гипотеза: read-only planner поверх текущего passport уменьшит ручное управление без новой платформы состояния; строгий offline classifier обновлений уменьшит шум без доверия удалённому тексту.
- Самый дешёвый опровергающий эксперимент: на существующей fixture проверить, что planner правильно ограничивает launch по dependency/cap/parent state, а classifier отклоняет неофициальный источник и малозначимое изменение.

## Контракт и инварианты

- Planner не изменяет passport, не создаёт задачи и не вызывает внешние инструменты; он только валидирует текущий snapshot и выдаёт bounded action plan.
- `paused`/`blocked` parent state запрещает новые `launch`; уже активные агенты возвращаются как `wait` или `hold` до безопасной контрольной точки.
- Новый запуск допускается только для `ready` subgoal, без активного агента на ту же подцель, при свободном global cap и валидном текущем passport.
- Завершённый agent при незавершённой subgoal требует `verify`; agent report сам по себе не переводит subgoal в `done`.
- Update classifier принимает только структурированный локальный JSON, не выполняет и не импортирует команды/код из источника и для OpenAI-кандидатов разрешает только `developers.openai.com`, `platform.openai.com` и `learn.chatgpt.com`.
- Каждый update candidate хранит отдельно `facts`, `inferences`, `assumptions`, измеримые impact dimensions и затронутые компоненты Harness.
- Значимость определяется прозрачным порогом; security/compatibility изменения могут пройти порог независимо от экономии времени. Низкий score не создаёт рекомендацию на внедрение.
- Старые passport schema v1 остаются валидными. Новая логика потребляет текущие поля и не создаёт второй canonical state.
- Только primary orchestrator меняет work item/passport и интегрирует результаты. Один writer на worktree.

## Карта воздействия

- Компоненты: новый минимальный `goal_orchestrator.py`; новый `update_impact.py`; их unit tests/fixtures; Goal Runner skill, README и architecture test; HRE-003 work/acceptance artifacts.
- Потребители: основной Goal-чат, Goal Runner worker/lead/verifier, пользователь при проверке обновлений.
- Совместимость: add-only CLI и документация; существующие команды/passport не меняют поведение.
- Данные: только bounded IDs, статусы, score dimensions, source URLs и короткие evidence fields; transcript и секреты запрещены.
- Безопасность: no network/no eval/no shell from candidate; source allowlist; fail-closed schema; planner read-only.
- Производительность: O(subgoals + agents + candidates), ожидаемо малые локальные файлы.
- Параллелизм: G01 и G02 независимы и пишутся в разных worktree; интеграция последовательная primary.
- Откат: отдельные атомарные commits по принятым подцелям либо revert HRE-003 commits. Глобальные установки не меняются.
- Риск: medium — новая управляющая рекомендация влияет на dispatch, но не выполняет действие самостоятельно.

## Goal runner state

- Chain ID: HRE-003
- Project root: `D:\6 Проекты\Харнес разработка`
- Data owner: пользователь — владелец workspace
- Risk class: medium
- External-side-effect boundary: local-only; no network, push, deploy, migration, deletion, global install, or secrets
- Parent outcome: read-only Parent Goal action planner plus evidence-separated significant-update radar
- Status: running
- Plan revision: 1
- Approved passport revision: 1
- Approval provenance: task `019fca39-7a3e-7a90-a726-a47e3c72dc19`; user message `Подтверждаю HRE-003 revision 1; AGENTS.md не менять; локальная реализация без push.`; 2026-08-11 Europe/Minsk
- Checkout/worktree policy: clean integration branch; one writer per isolated worker worktree; primary serializes integration
- Commit policy: isolated-worker checkpoints after acceptance; primary integration; no push
- Current laziness-ladder rung: 2 — Python stdlib plus existing validator/JSON contracts
- Rejected lower rungs: YAGNI fails because orchestration and update filtering are explicitly requested; documentation alone cannot mechanically reject unsafe launch plans or untrusted/noisy update records
- Current verified subgoal: P0 — revision-1 passport valid and prechange gate passed with the two expected planning files as the only worktree changes
- Next minimal slice and acceptance check: receive matching orientation acknowledgements for G01/G02, revalidate the current passport immediately before writes, then authorize the two isolated minimal slices
- Executable plan snapshot: `.harness/work/hre-003.passport.json`
- Measurement treatment IDs: baseline `manual-goal-updates-v1` | treatment `autopilot-radar-v1`
- Metrics path/schema: `.harness/metrics/hre-003.jsonl` / schema 1
- Global agent cap: 2; delegation depth: 1; active agents: 0
- Standing chain authorization: approved; scope: bounded continuation for listed HRE-003 subgoals only
- Archive policy: final explicit command only

## Подцели

| ID | Результат | Depends on | Wave | Ownership | Risk | Execution/model | Status | Acceptance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | Revision-1 passport, impact map and clean prechange evidence without editing `AGENTS.md` | none | 1 | primary / plan artifacts | low | primary / sol | done | validator PASS; prechange PASS; 57 tests |
| G01 | Read-only parent action planner computes bounded launch/wait/verify/hold/complete actions from a valid current passport | P0 | 2 | `goal_orchestrator.py`, targeted tests | medium | worker / terra | ready | negative and state-transition unit tests PASS |
| G02 | Offline update impact radar rejects untrusted input and surfaces only threshold-significant official changes with fact/inference/assumption separation | P0 | 2 | `update_impact.py`, targeted tests and template | medium | worker / terra | ready | schema/source/threshold unit tests PASS |
| G03 | Goal Runner and README define Play/resume semantics, child-task boundaries, current model routing and update review flow without claiming automatic UI control | G01,G02 | 3 | skill/docs/architecture test | low | primary / sol | planned | architecture test and manual contract review PASS |
| G04 | Independent verifier reproduces correctness/security cases and performs a separate simplify review | G01,G02,G03 | 4 | read-only integrated tree | medium | verifier / sol-high | planned | independent report ACCEPT, no unresolved blocker |
| G05 | Fresh acceptance, full suite and strict release prove the integrated HRE-003 result | G04 | 5 | primary / acceptance and journal | medium | primary / sol | planned | targeted, full, architecture and strict release PASS |

## План проверок

1. G01: targeted unit tests for invalid passport, cap, duplicate active work, paused parent, verify-before-done and deterministic JSON.
2. G02: targeted unit tests for official-domain allowlist, strict types, fact/inference/assumption separation, security override and significance threshold.
3. G03: `scripts/Test-GoalRunnerArchitecture.ps1` plus diff review against actual CLI behavior.
4. G04: independent read-only negative-oracle reproduction, correctness pass, then simplify pass.
5. G05: full unittest suite; HRE-003 passport validator; postchange and strict release gates; fresh acceptance evidence.

## Agent registry

| Agent | Subgoal | Role/model | Worktree | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| `hre003-g01-worker` | G01 | worker / terra-medium | `.worktrees/hre-003-g01` | orienting | Must acknowledge bounded planner contract before writes. |
| `hre003-g02-worker` | G02 | worker / terra-medium | `.worktrees/hre-003-g02` | orienting | Must acknowledge offline update-radar contract before writes. |

## Действия, требующие отдельного разрешения

- Любой network fetch из runtime-кода, scheduled automation, глобальная установка/обновление Codex или Graphify, plugin migration, push, PR, deploy, публикация, удаление или работа с секретами.

## Журнал доказательств

| Время | Проверка | Результат | Вывод |
| --- | --- | --- | --- |
| 2026-08-11 | Orientation: git/status, recent commits, current work items, official OpenAI docs, Graphify query | PASS | Repo clean; branch ahead 1; control and update gaps localized; no implementation started. |
| 2026-08-11 | HRE-003 passport validator and `Invoke-HarnessGate.ps1 -Stage prechange` | PASS | Passport valid; 57 tests, benchmark, bootstrap and architecture checks passed; only the two expected planning files were reported as changes. |
| 2026-08-11 | User approval of HRE-003 revision 1 | APPROVED | Local bounded implementation authorized; `AGENTS.md` and push remain excluded. |
