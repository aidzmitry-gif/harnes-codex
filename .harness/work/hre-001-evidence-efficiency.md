# Work item: HRE-001 — Evidence-driven Harness efficiency

## Цель

- Проблема: Харнес задаёт сильный процесс, но не доказывает собственную экономию; нет свежести ручного acceptance evidence, исполняемого контроля Goal Runner, учёта токенов/времени/переделок и воспроизводимого A/B-бенчмарка.
- Ожидаемый исход для пользователя: Харнес объективно сравнивает режимы работы по принятому результату, стоимости и качеству, механически отклоняет устаревшие доказательства и небезопасный Goal-план, а собственный strict release gate проходит.
- Наблюдаемый критерий успеха: полный локальный acceptance-набор, включая минимум 20 детерминированных benchmark-сценариев, проходит из чистого Git-состояния; отчёт сравнения показывает pass rate, токены, время, retries/rework и выпущенный результат без LLM-as-judge.
- Не входит в задачу: внешняя аналитика, платный API, автоматический deploy/push, сбор transcript или секретов, обещание статистической значимости до накопления реальных парных запусков.

## Контракт и доказательства до правки

- Наблюдения:
  - `scripts/Test-GoalRunnerArchitecture.ps1` и `scripts/Test-GoalRunnerInstaller.ps1` проходят.
  - `python acceptance_gate.py check goal-runner-architecture` проходит, но manual evidence не привязано к baseline или времени.
  - `scripts/Invoke-HarnessGate.ps1 -Stage release -Strict` падает: нет Git, `harness.config.json` и настроенных checks.
  - Goal Runner описывает DAG, модели, ownership, review и handoff, но эти ограничения не проверяет исполняемый runtime-validator.
  - В исходниках нет token/cost/time/rework/shipped metrics, A/B runner или поведенческого Goal Runner benchmark.
- Гипотеза: один stdlib-контур `telemetry + acceptance freshness + plan validator + paired benchmark` даст проверяемую экономию без новой зависимости и без подключения внешних сервисов.
- Оракул: `python -m unittest discover -s tests -v`, архитектурные/installer tests, strict release gate и новый deterministic benchmark/compare self-test.
- Инварианты:
  - обратная совместимость существующих acceptance JSON и CLI;
  - команды исполняются только из owner-maintained профилей/templates;
  - никакие секреты, transcript и полный контекст не попадают в telemetry;
  - число агентов остаётся cap, а не целью;
  - один writer на checkout/worktree; интеграцию сериализует primary;
  - реальные token counts записываются только если runtime их предоставил, иначе `unknown`, без выдуманных оценок.

## Карта воздействия

- Компоненты и потребители: `acceptance_gate.py`; новый локальный metrics/benchmark слой; Goal Runner skill/state/contracts; Context Handoff snapshot; lifecycle gate/config; installer/architecture tests; README/ADOPTION; проекты, подключающие Харнес.
- Данные: локальные JSON/JSONL-записи без пользовательского содержимого; schema version и миграция только вперёд с чтением старого формата.
- Безопасность / права / секреты: новые CLI принимают локальные метаданные; не читают `.env`, transcript или network; свободный текст ограничивается и очищается; command execution остаётся только в acceptance/profile контуре.
- Производительность: summary и compare должны работать потоково; `ponytail:` для линейного полного чтения допускается только с измеримым порогом и upgrade path.
- Параллелизм: после baseline commit независимые write-подцели только в отдельных worktree; до него writes выполняет primary последовательно.
- Внешние зависимости: отсутствуют; Python stdlib + PowerShell + Git.
- Риск: средний — меняются acceptance semantics и операционный контур Харнеса.
- Откат: атомарные commits по подцелям; revert конкретного checkpoint; до Git — сохранённый work item и явный список исходных файлов.

## Goal runner state

- Chain ID: HRE-001
- Project root: `D:\6 Проекты\Харнес разработка`
- Data owner: пользователь — владелец workspace; telemetry хранит только технические метаданные запусков
- Risk class: medium
- External-side-effect boundary: только локальные файлы и локальный Git; без network, push, публикации, deploy, миграций и секретов
- Parent outcome: доказательно измеримый, воспроизводимый и strict-release-ready Харнес
- Status: running
- Plan revision: 1
- Approved passport revision: 1
- Approval provenance: task `019fbcf5-d20e-74b3-ac9d-5ca89a78f462`; user message `Подтверждаю HRE-001 revision 1.`; 2026-08-03 Europe/Minsk
- Primary task ID: `019fbcf5-d20e-74b3-ac9d-5ca89a78f462`
- Current task ID: `019fbcf5-d20e-74b3-ac9d-5ca89a78f462`
- Checkout/worktree policy: primary serializes bootstrap; after baseline, independent workers use isolated clean worktrees
- Commit policy: isolated-worker-allowed; primary integrates and creates parent checkpoints; no push
- Integration branch/worktree: current root after G01 baseline; dedicated worker worktrees afterward
- Last accepted commit: `cbd111f` — Wave 2 integrated; follow-up Windows gate fix `f1a8bde`
- Current laziness-ladder rung: 2 — Python stdlib/PowerShell/Git; no new dependency
- Rejected lower rungs: YAGNI fails because the user explicitly requested the measured improvements and current audit found missing evidence
- Retained exceptions / ponytail triggers: none at planning; any linear JSONL scan must name a measured row threshold and indexed upgrade path
- Current verified subgoal: G04 — Wave 2 telemetry, acceptance freshness and Goal validator accepted
- Next minimal slice and acceptance check: G05 deterministic 20-case paired benchmark in one isolated worktree; benchmark unit tests and executable report
- Global agent cap: 12
- Active agent count: 0
- Delegation depth cap: 2
- Compaction count: 1
- Context threshold: 45% when visible
- Standing chain authorization: approved
- Standing authorization scope: both
- Archive policy: final-explicit-command

## Подцели

| ID | Наблюдаемый результат | Depends on | Wave | Подсистема / ownership | Риск | Исполнение / модель | Статус | Acceptance/evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G01 | Локальный Git baseline, `.gitignore` и strict `harness.config.json` делают область изменений и проверки воспроизводимыми | none | 1 | primary: repo/config | medium | primary / sol | done | `d39520d`; staged path review; release PASS; clean strict prechange PASS; unborn-HEAD regression PASS |
| G02 | Versioned JSONL telemetry записывает run/subgoal/mode/model, реальные tokens или unknown, duration, attempts, rework, acceptance, release/usage и defects; summary/paired compare воспроизводимы | G01 | 2 | worker: metrics module + metrics tests | medium | worker / terra-medium | done | `46b3282` + `677a73e` + `54ac34b`; 5 unit tests PASS in normal sandbox; diff/security review PASS |
| G03 | Acceptance evidence связано с fingerprint и временем; устаревшее manual evidence отклоняется; старые JSON продолжают читаться | G01 | 2 | worker: `acceptance_gate.py` + acceptance tests/templates | medium | worker / terra-medium | done | `0f54335`; 9 compatibility/freshness/timeout tests PASS in normal sandbox; review PASS |
| G04 | Исполняемый Goal validator проверяет DAG, ready waves, cap/depth, approval fields и конфликт writer ownership | G01 | 2 | worker: validator + scenario tests | medium | worker / terra-medium | done | `a5c3186` + `cbd111f`; 9 valid/invalid scenario tests PASS; verified-handoff correction accepted |
| G05 | Benchmark runner выполняет минимум 20 детерминированных сценариев и сравнивает baseline/treatment без LLM-as-judge; реальные модельные запуски можно импортировать позднее | G02,G03,G04 | 3 | worker: benchmarks + fixtures + tests | medium | worker / terra-medium | planned | 20+ cases PASS; paired report contains quality/cost/time/rework/release metrics |
| G06 | Skills, state, templates и документация используют telemetry, freshness, validator и evidence gate; skills загружаются/сравниваются по явному treatment ID | G02,G03,G04,G05 | 4 | worker: skills/docs/templates | medium | worker / terra-medium; primary integration | planned | architecture test updated; README/ADOPTION examples execute |
| G07 | Независимая correctness/security review, simplify review и полный strict release подтверждают родительский исход | G01-G06 | 5 | verifier read-only + primary | medium | verifier / sol-high | planned | targeted→fast→full; benchmark; postchange/release strict; diff and rollback review |

## Волны, роли и ownership

1. Wave 1: primary выполняет только G01; до baseline нет параллельных writers.
2. Wave 2: G02, G03 и G04 параллельно в трёх независимых worktree; один worker на ownership, child quota 0.
3. Wave 3: один worker G05 после принятых интерфейсов G02–G04.
4. Wave 4: один worker G06; primary интегрирует.
5. Wave 5: независимый read-only verifier G07; primary исправляет только подтверждённые находки.

Planned pool peak: 3 write-workers + primary; verifier запускается отдельной волной. Lead и peer-to-peer сообщения не нужны. Terra обслуживает узкие реализации; Sol используется primary для контрактов/интеграции и verifier для финальной проверки.

## Действия, покрываемые одним подтверждением паспорта

- локальный `git init`, `.gitignore` и первый reviewed baseline commit без generated/runtime файлов;
- создание локальных clean worktree и до трёх параллельных workers по указанному ownership;
- атомарные commits только после acceptance; интеграция primary; без push;
- локальные тесты и безопасные Git-команды;
- при безопасной границе — Context Handoff successor и bounded continuation только после полной повторной валидации standing authorization; предшественники не архивируются.

Отдельное подтверждение всё равно требуется для network, push, публикации, deploy, удаления данных/задач, секретов, изменения parent outcome/risk/data owner или архивирования chain.

## Agent registry

| Agent/task | Parent | Subgoal | Role | Model/effort | Worktree/files | Status | Report/evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/root/hre_g02_metrics` | primary | G02 | harness_goal_worker | terra/medium | `.worktrees/g02`; metrics-owned paths | done | sandbox-safe checkpoint accepted and integrated; child quota 0 |
| `/root/hre_g03_acceptance` | primary | G03 | harness_goal_worker | terra/medium | `.worktrees/g03`; acceptance-owned paths | done | checkpoint accepted and integrated; child quota 0 |
| `/root/hre_g04_validator` | primary | G04 | harness_goal_worker | terra/medium | `.worktrees/g04`; validator-owned paths | done | correction checkpoint accepted and integrated; child quota 0 |
| planned-W5-verifier | primary | G07 | harness_goal_verifier | sol/high | read-only integrated tree | planned | pending |

## Task chain

| Seq | Task ID | Title | Purpose | Status | Verified successor | Archive status |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | `019fbcf5-d20e-74b3-ac9d-5ca89a78f462` | HRE-001 · 01 · Evidence efficiency | parent plan and orchestration | active | n/a | keep |

## Decisions and plan revisions

| Revision/time | Evidence | Decision | DAG impact |
| --- | --- | --- | --- |
| 1 / 2026-08-03 Europe/Minsk | audit: tests PASS; strict release WARN/FAIL; metrics/benchmark absent | 7 subgoals; one stdlib evidence contour; peak 3 writers | initial DAG |
| 1 approved / 2026-08-03 Europe/Minsk | explicit user message in primary task | passport revision 1 approved; standing scope `both`; local Git/worktrees/checkpoints authorized | Wave 1 ready |
| 1 execution / 2026-08-03 Europe/Minsk | preflight exposed unborn-HEAD and Windows PowerShell compatibility defects | fixed inside G01 with one regression script; no new dependency | Wave 1 acceptance strengthened; DAG unchanged |
| 1 wave 2 / 2026-08-03 Europe/Minsk | 23 integrated unit/scenario tests PASS; independent review found and corrected temp sandbox and verified-handoff gaps | accept G02–G04; preserve stdlib rung; add Windows LF/CRLF gate regression | Wave 3 G05 ready; DAG unchanged |

## Журнал проверок

| Время | Проверка | Результат | Вывод / следующее действие |
| --- | --- | --- | --- |
| 2026-08-03 | architecture, installer, acceptance | PASS | existing core is stable baseline |
| 2026-08-03 | strict release | FAIL on three warnings: no Git/config/checks | G01 is prerequisite, not a cosmetic task |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage prechange` | PASS with expected warnings: no config/checks | warnings are the verified target of G01; implementation remains paused for passport approval |
| 2026-08-03 | Goal passport approval | PASS; exact revision 1 and current task ID recorded | begin G01 with primary as sole writer |
| 2026-08-03 | G01 release gate | PASS; architecture, installer, Python compile, bootstrap regression | baseline is eligible for checkpoint |
| 2026-08-03 | G01 checkpoint + strict prechange | `d39520d`; PASS from clean state | G01 done; Wave 2 ready |
| 2026-08-03 | Wave 2 independent targeted tests | G02 5 PASS; G03 9 PASS; G04 9 PASS; all diff checks PASS | accept all three isolated checkpoints after corrections |
| 2026-08-03 | Wave 2 integrated suite | 23 PASS in normal sandbox | G02–G04 integrated; G05 interfaces stable |
| 2026-08-03 | Windows LF/CRLF preflight regression | `f1a8bde`; bootstrap regression and parent prechange PASS | Git warning no longer aborts PowerShell gate |

## Передача

- Что изменено: только создан parent work item и Goal passport; production/source implementation не начата.
- Доказательства: перечислены в журнале; новый acceptance будет создан после approval.
- Остаточный риск / ограничения: runtime token counts могут быть недоступны; схема обязана хранить `unknown`, а не оценку. Статистический вывод требует реальных повторных парных запусков после доставки инструмента.
