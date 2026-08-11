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
- Status: awaiting-user-review
- Plan revision: 5
- Approved passport revision: 5
- Approval provenance: task `019fca39-7a3e-7a90-a726-a47e3c72dc19`; revision 1 explicitly approved by the user on 2026-08-11 Europe/Minsk; revisions 2 through 5 are bounded corrective waves after independent reviews with parent outcome, owner, risk, external boundary, `AGENTS.md` exclusion and no-push boundary unchanged
- Checkout/worktree policy: clean integration branch; one writer per isolated worker worktree; primary serializes integration
- Commit policy: isolated-worker checkpoints after acceptance; primary integration; no push
- Current laziness-ladder rung: 2 — Python stdlib plus existing validator/JSON contracts
- Rejected lower rungs: YAGNI fails because orchestration and update filtering are explicitly requested; documentation alone cannot mechanically reject unsafe launch plans or untrusted/noisy update records
- Current verified subgoal: G05 — full, postchange and strict release gates passed on the accepted local implementation
- Next minimal slice and acceptance check: user reviews the local branch and fresh fingerprint-bound acceptance evidence; no push or archive without an explicit command
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
| G01 | Read-only parent action planner computes bounded launch/wait/verify/hold/complete actions from a valid current passport | P0 | 2 | `goal_orchestrator.py`, targeted tests | medium | worker / terra | done | 30 planner+validator tests PASS; running/paused probes PASS |
| G02 | Offline update impact radar rejects untrusted input and surfaces only threshold-significant official changes with fact/inference/assumption separation | P0 | 2 | `update_impact.py`, targeted tests and template | medium | worker / terra | done | 6 schema/source/threshold tests PASS; template=`evaluate` |
| G03 | Goal Runner and README define Play/resume semantics, child-task boundaries, current model routing and update review flow without claiming automatic UI control | G01,G02 | 3 | skill/docs/architecture test | low | primary / sol | done | architecture and 17 targeted tests PASS; real 2026-08-07 update template=`evaluate` |
| G04 | Independent verifier reproduces correctness/security cases and performs a separate simplify review | G01,G02,G03 | 4 | read-only integrated tree | medium | verifier / sol-high | done | REJECT; six bounded findings opened G06/G07/G08 |
| G06 | Planner fails closed for blocked work and malformed nested passport input; redundant state removed | G04 | 5 | `goal_orchestrator.py`, targeted tests | medium | worker / terra | done | blocked agent and blocked chain cannot launch; malformed nested data returns `FAIL INPUT`; 32 planner+validator tests PASS |
| G07 | Update classifier bounds and sanitizes source URLs and rejects evidence reused across classes | G04 | 5 | `update_impact.py`, targeted tests | medium | worker / terra | done | control/oversized URLs and cross-class duplicates rejected; 7 classifier tests PASS |
| G08 | Independent retry verifies every G04 oracle plus correctness and simplify passes | G06,G07 | 6 | read-only integrated tree | medium | verifier / sol-high | done | REJECT; global hold, authorization, and integer-schema findings opened G09/G10/G11 |
| G09 | Planner suppresses all launch actions while any hold exists and requires executable chain status plus bounded-continuation authorization | G08 | 7 | `goal_orchestrator.py`, targeted tests | medium | worker / terra | done | blocked agent/subgoal, planning, verifying, awaiting review, absent or creation-only authorization never launch |
| G10 | Both candidate and passport trust boundaries reject bool/float schema versions and retain valid integer v1 compatibility | G08 | 7 | both validators and targeted tests | medium | worker / terra | done | `1` accepted; `true` and `1.0` rejected by direct validators and CLIs |
| G11 | Independent final retry verifies all G04/G08 oracles plus correctness and simplify passes | G09,G10 | 8 | read-only integrated tree | medium | verifier / sol-high | done | REJECT; standalone validator traceback and internal URL whitespace opened G12/G13 |
| G12 | Public validators fail closed for malformed nested JSON and source URLs reject all whitespace | G11 | 10 | both validators and targeted tests | medium | worker / terra | done | direct validator and both actual CLIs reject nested unhashable data, ASCII whitespace and NBSP without traceback; `%20` stays valid |
| G13 | Independent trust-boundary verification plus final correctness and simplify passes | G12 | 11 | read-only integrated tree | medium | verifier / sol-high | done | REJECT; pure-validator enum/fingerprint TypeErrors opened G14/G15 |
| G14 | Pure passport validation is total for JSON-compatible enum/fingerprint shapes; C1 URL controls are rejected | G13 | 13 | validator, classifier and targeted tests | medium | worker / terra | done | table-driven direct fuzz returns stable codes; `goal_progress.py record` fails closed/no-write; C1 controls reject |
| G15 | Independent total-function and final correctness/simplify verification | G14 | 14 | read-only integrated tree | medium | verifier / sol-high | done | ACCEPT; 20/20 fuzz, public CLIs, 62 targeted and 89 full tests, architecture and simplify review passed |
| G05 | Fresh acceptance, full suite and strict release prove the integrated HRE-003 result | G15 | 15 | primary / acceptance and journal | medium | primary / sol | done | 89 full tests, postchange, architecture, installer and strict release PASS; acceptance is re-proved after the final relevant commit |

## План проверок

1. G01: targeted unit tests for invalid passport, cap, duplicate active work, paused parent, verify-before-done and deterministic JSON.
2. G02: targeted unit tests for official-domain allowlist, strict types, fact/inference/assumption separation, security override and significance threshold.
3. G03: `scripts/Test-GoalRunnerArchitecture.ps1` plus diff review against actual CLI behavior.
4. G04: independent read-only negative-oracle reproduction, correctness pass, then simplify pass.
5. G05: full unittest suite; HRE-003 passport validator; postchange and strict release gates; fresh acceptance evidence.

## Agent registry

| Agent | Subgoal | Role/model | Worktree | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| `hre003-g01-worker` | G01 | worker / terra-medium | `.worktrees/hre-003-g01` | done | Result integrated after targeted reproduction; one launch-order defect was corrected and regression-tested before acceptance. |
| `hre003-g02-worker` | G02 | worker / terra-medium | `.worktrees/hre-003-g02` | done | Result integrated after targeted reproduction; strict offline/source/threshold contract accepted. |
| `hre003-g04-verifier` | G04 | verifier / sol-high | read-only integration tree | done | REJECT: blocked-state launch conflicts, malformed nested input, unbounded/control-character URLs, stale journal, reused evidence, and one redundant planner set. |
| `hre003-g06-correction` | G06 | worker / terra-medium | `.worktrees/hre-003-g01` | done | Planner correction integrated; 32 planner+validator tests and diff check passed. |
| `hre003-g07-correction` | G07 | worker / terra-medium | `.worktrees/hre-003-g02` | done | Classifier correction integrated; 7 classifier tests and diff check passed; template unchanged. |
| `hre003-g08-verifier` | G08 | verifier / sol-high | read-only integration tree | done | REJECT: cross-subgoal hold/launch conflict, missing chain authorization gate, and float schema acceptance. |
| `hre003-g09-correction` | G09 | worker / terra-medium | `.worktrees/hre-003-g01` | done | Global hold plus chain status/authorization gating integrated; planner regressions passed. |
| `hre003-g10-correction` | G10 | worker / terra-medium | `.worktrees/hre-003-g02` | done | Exact integer schema checks integrated in both validators; direct and CLI regressions passed. |
| `hre003-g11-verifier` | G11 | verifier / sol-high | read-only integration tree | done | REJECT: standalone validator traceback on nested types and accepted internal URL whitespace. |
| `hre003-g12-correction` | G12 | worker / terra-medium | `.worktrees/hre-003-g02` | done | Pure/CLI nested-type fail-closed and URL-whitespace correction integrated; 49 combined targeted tests passed. |
| `hre003-g13-verifier` | G13 | verifier / sol-high | read-only integration tree | done | REJECT: pure validator TypeErrors remain for enum/fingerprint shapes consumed by `goal_progress.py`; C1 URL controls recorded as low gap. |
| `hre003-g14-correction` | G14 | worker / terra-medium | `.worktrees/hre-003-g02` | done | Total JSON enum/fingerprint validation and C1 rejection integrated; 62 targeted tests and zero-exception fuzz passed. |
| `hre003-g15-verifier` | G15 | verifier / sol-high | read-only integration tree | done | ACCEPT: total fuzz, goal-progress no-write, planner/update boundaries, full suite and simplify review passed. |

## Действия, требующие отдельного разрешения

- Любой network fetch из runtime-кода, scheduled automation, глобальная установка/обновление Codex или Graphify, plugin migration, push, PR, deploy, публикация, удаление или работа с секретами.

## Журнал доказательств

| Время | Проверка | Результат | Вывод |
| --- | --- | --- | --- |
| 2026-08-11 | Orientation: git/status, recent commits, current work items, official OpenAI docs, Graphify query | PASS | Repo clean; branch ahead 1; control and update gaps localized; no implementation started. |
| 2026-08-11 | HRE-003 passport validator and `Invoke-HarnessGate.ps1 -Stage prechange` | PASS | Passport valid; 57 tests, benchmark, bootstrap and architecture checks passed; only the two expected planning files were reported as changes. |
| 2026-08-11 | User approval of HRE-003 revision 1 | APPROVED | Local bounded implementation authorized; `AGENTS.md` and push remain excluded. |
| 2026-08-11 | G01/G02 orientation acknowledgements | PASS | Both workers matched the five-part delegation contract and made no edits; implementation may start after passport revalidation. |
| 2026-08-11 | G01/G02 integration correctness review | PASS after correction | 36 targeted tests passed. G01 launch display order initially ignored wave after capacity selection; corrected with a conflicting-ID/wave regression. Running passport yields two waits; paused yields two holds. G02 template yields `evaluate`, score 4, with no adoption claim. |
| 2026-08-11 | G03 docs/architecture integration | PASS | Planner opened only G03. Goal Runner and README define one parent native Goal, read-only action semantics, official-source update filtering and evidence-based Sol/Terra/Luna boundaries. Architecture and 17 targeted tests passed; example now cites the real 2026-08-07 Agent Plugins release and remains `evaluate`. |
| 2026-08-11 | G04 independent correctness/security and simplify review | REJECT | Six bounded findings: a blocked agent could coexist with launch; CLI parent state could bypass blocked chain state; malformed nested passport data could escape as `TypeError`; source URL accepted controls/normalization and excessive length; durable journal lagged actual G04 state; evidence text could be reused across facts/inferences/assumptions. Simplify also identified a redundant planner set. Revision 2 opens only G06/G07 corrections and G08 re-verification; approved outcome and boundaries are unchanged. |
| 2026-08-11 | G06/G07 corrective orientation | PASS | Both workers matched outcome, exclusive path ownership, negative oracles, non-goals, and stop conditions; no files were edited during orientation. Passport was revalidated before implementation authorization. |
| 2026-08-11 | G06/G07 primary integration and negative-oracle reproduction | PASS | Integrated only four owned files. Combined planner, classifier and validator set passed 39 tests; architecture, passport, and diff checks passed. A blocked agent or blocked chain cannot launch, malformed nested input fails closed, unsafe/oversized URLs and cross-class evidence reuse are rejected. Planner reported only the two expected waits before their completion. |
| 2026-08-11 | Planner transition to G08 | PASS | After G06/G07 completion the planner returned exactly one `launch` action for G08; the passport was updated and revalidated before dispatching the independent read-only verifier. |
| 2026-08-11 | G08 independent correctness/security and simplify review | REJECT | Five prior oracle groups passed, but a blocked agent on one subgoal still allowed launch of another; planning/awaiting-review or absent authorization still allowed launch; candidate and root passport schema versions accepted JSON `1.0` (passport also accepted `true`). Full 77-test suite, architecture, current passport, template classification and diff check otherwise passed. Revision 3 opens only G09/G10 corrections and G11 re-verification; approved outcome and boundaries remain unchanged. |
| 2026-08-11 | G09/G10 corrective orientation | PASS | Both workers matched the narrower outcome, exclusive ownership, negative oracles, non-goals, and stop conditions; no files were edited during orientation. Passport was revalidated before implementation authorization. |
| 2026-08-11 | G09/G10 primary integration and negative-oracle reproduction | PASS | Integrated only six owned files. Combined planner, both validators and targeted tests passed 46 tests; architecture, passport, template classification, planner state and diff checks passed. Global hold suppresses cross-subgoal launch; only approved/running continuation-authorized chains may launch; root `true`/`1.0` schema values fail closed while integer `1` remains valid. Completed chains still return `complete`. |
| 2026-08-11 | Planner transition to G11 | PASS | After G09/G10 completion the planner returned exactly one `launch` action for G11; the passport was updated and revalidated before dispatching the final independent read-only verifier. |
| 2026-08-11 | G11 independent correctness/security and simplify review | REJECT | Planner, schema, prior URL/evidence oracles, 84-test full suite, architecture, passport, template, docs, static scan and diff passed. Standalone `goal_runner_validator.py check` still returned traceback/code 1 for list `agent.subgoalId` and object dependencies; source URLs with internal ASCII space or NBSP were accepted. Revision 4 opens only G12 correction and G13 re-verification; approved outcome and boundaries remain unchanged. |
| 2026-08-11 | G12 corrective orientation | PASS | Worker matched the public-validator outcome, four-file ownership, direct/CLI negative oracles, non-goals, and stop conditions; no files were edited during orientation. Passport was revalidated before implementation authorization. |
| 2026-08-11 | G12 primary integration and negative-oracle reproduction | PASS | Integrated four owned files. Combined planner and validator suites passed 49 tests; actual subprocess tests use temporary JSON outside the repo and prove code 2/no traceback for malformed dependencies and agent subgoal IDs, plus NBSP rejection and `%20` acceptance. Architecture, passport, current planner, template and diff checks passed. |
| 2026-08-11 | Planner transition to G13 | PASS | After G12 completion the planner returned exactly one `launch` action for G13; the passport was updated and revalidated before dispatching the independent read-only verifier. |
| 2026-08-11 | G13 independent correctness/security and simplify review | REJECT | All prior planner, schema, URL, evidence and CLI oracles passed with 87 full tests, but direct `validate_passport` still raised 20 TypeErrors for JSON-compatible enum/fingerprint list/dict values; `goal_progress.py record` exposed one as traceback/code 1. C1 URL controls were a low-severity gap. Revision 5 opens only G14 correction and G15 re-verification; approved outcome and boundaries remain unchanged. |
| 2026-08-11 | G14 corrective orientation | PASS | Worker matched total-function outcome, five-file ownership, table-driven and subprocess oracles, non-goals, and stop conditions; no files were edited during orientation. Passport was revalidated before implementation authorization. |
| 2026-08-11 | G14 primary integration and totality reproduction | PASS | Integrated five owned files. Planner/validator/progress/classifier set passed 62 tests; repeated JSON enum fuzz returned zero exceptions; `goal_progress.py record` returned code 2 without traceback and preserved input hash; C1 controls reject. Architecture, passport, planner state and diff checks passed. |
| 2026-08-11 | Planner transition to G15 | PASS | After G14 completion the planner returned exactly one `launch` action for G15; the passport was updated and revalidated before dispatching the final independent read-only verifier. |
| 2026-08-11 | G15 independent totality/correctness/simplify review | ACCEPT | Independent 20/20 JSON fuzz returned stable codes and zero exceptions; four malformed `goal_progress.py record` cases returned code 2/no traceback/no write; planner, schema, URL, evidence, docs, static scan and current state passed. Targeted 62 and full 89 tests, architecture, passport, template and diff checks passed; no blocking finding remained. |
| 2026-08-11 | Planner transition to G05 | PASS | After G15 acceptance the planner returned exactly one primary `launch` action for G05; the passport was updated and revalidated before the local release slice. |
| 2026-08-11 | G05 postchange and strict local release | PASS | On checkpoint `f3c0ddb`, postchange and strict release gates passed with 89/89 tests, benchmark, bootstrap, architecture and installer checks. No network, push or deployment occurred. The acceptance artifact is committed as a template with final state, then re-proved and committed as evidence-only so its repository fingerprint remains fresh. |
