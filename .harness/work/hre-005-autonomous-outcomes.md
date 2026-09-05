# Work item: HRE-005 — автономное выполнение до проверяемого результата

## Цель

- Запрос: внедрить улучшения из аудита Harness и сессий; пользователь дополнительно попросил максимальную автономность GPT.
- Исход: после одного утверждения ограниченного плана агент сам реализует, проверяет и исправляет все безопасные пункты; готовность подтверждается наблюдаемым сценарием, а незавершённая проверка или локальный blocker не теряются.
- Статус: awaiting-user-review. G01–G06 локально завершены; release и свежая техническая приёмка 5/5 PASS, независимые correctness/simplify review приняты. Пользователь явно подтвердил HRE-005 revision 1 в текущей задаче 2026-09-05; user acceptance не подменяется технической приёмкой.
- Не входит: изменение AGENTS.md; commit/push/PR/deploy; реальные платежи/CRM/production; установка/обновление глобальных skills; запись в другие проекты или сводный Graphify; изменение активных автоматизаций; запуск платного benchmark; миграция живого radar state; архивирование и создание обычных задач.
- Локальные изменения Goal Runner skill входят в план, но защищённые .agents пути требуют штатной проверки доступа. Отказ не обходить; незатронутые пункты продолжить.

## Исходные наблюдения до реализации и проверяемая гипотеза

- База: clean HEAD c60a0e0, ветка codex/hre-004-update-watcher. Перед планом prechange PASS, 97 tests / 5.299 s; общий gate около 10 s.
- AGENTS.md SHA-256: B0184C9D679DE0622E8F42F9673132007C3BB4E3BF18AF85A44845E9E4D116BF.
- update_radar.py сохраняет id/digest до оценки применимости; точный повтор исключается из результата. Ранее воспроизведено без дисковых записей: meaningful-updates -> no-meaningful-updates, local evaluation не выполнялась.
- goal_orchestrator.py запрещает все launch при любом hold; tests/test_goal_orchestrator.py закрепляет это поведение.
- .harness/CONTEXT.md всё ещё ссылается на HRE-001/main/d3ac1db, а текущий checkout содержит HRE-004. Использовать snapshot без проверки нельзя.
- Существующие acceptance_gate.py и harness_metrics.py уже имеют fresh evidence, pairKey, rework, accepted/released/used и nullable token counts. Не создавать второй механизм.
- Сессии показали дополнительные запросы пользователя после «готово» и длительные повторные monitor runs. Это мотивирует сценарную приёмку и дешёвую проверку prerequisites, но не доказывает процент будущей экономии.
- Гипотеза: компактный утверждённый контракт + независимое продвижение + сохранённая pending evaluation уменьшают повторные вопросы/потерянные проверки, не ослабляя безопасность.
- Самые дешёвые оракулы: unittest для повторного radar scan, DAG с blocked и независимым ready, ручной воспроизводимый сценарий с ожидаемым пользовательским результатом.
- Graphify: использован существующий graph read-only, query budget 1100; это навигация, не доказательство свежести. Нового графа/памяти не создавать.

## Контракт автономности

После одобрения revision 1:
1. Самостоятельно проходить все G01–G06, а не завершать работу после первой зелёной подзадачи.
2. Не спрашивать повторно разрешение на перечисленные локальные шаги, тесты, исправления в исходном контракте, чтение нужного контекста и независимые read-only проверки.
3. Самостоятельно выбирать минимальное решение и исполнителя в ограниченном пуле. Primary — единственный writer. Обнаружение и ревью можно распараллеливать; записи только последовательно.
4. Один native Goal в текущей задаче после одобрения; без новых обычных задач и worktrees в этой цепочке.
5. При сбое уточнить причину и проверить исправление; соблюдать NO_PROGRESS и остановку после двух независимых неуспешных диагностик. Не повторять бессмысленные попытки.
6. Локальная блокировка останавливает зависимый участок; parent pause/block, безопасность, права и отсутствие standing authorization запрещают общий dispatch.
7. Waiting-for-access/user — отдельное состояние с конкретным условием продолжения. Не делать тяжёлый повторный анализ без изменения prerequisites/evidence.
8. Сообщать значимые промежуточные результаты и один пакет нерешённых вопросов; не требовать команды «делай дальше» внутри утверждённых границ.
9. Не считать local verified равным deployed или user accepted; отсутствие токенов/доказательств хранить как unknown/null.
10. Отдельно согласовывать расширение результата, новые деньги/доступы, внешнюю запись, необратимые действия или снятие ограничений. Не обещать фоновую работу вне активной Goal/существующего scheduler.

## Карта воздействия

- Компоненты: update_radar.py, goal_orchestrator.py, их tests; templates, ENGINEERING_LOOP, README и локальный Goal Runner skill; текущий контекст и HRE-005 артефакты.
- Потребители: planner caller, report-only radar caller и будущие локальные Goal задачи.
- Данные: новая логика pending/resolved radar должна читать legacy state без потери id/digest; тестировать только изолированные fixtures/temp. Живой .harness/runtime/update-radar-state.json не читать/перезаписывать ради миграции в этой цепочке.
- Безопасность: official source allowlist, строгая схема, лимиты, конфликт id/digest, state path confinement и атомарная запись сохраняются. Не хранить transcript, секреты или source instructions в telemetry/state.
- Совместимость: существующие метрики schema 1 и acceptance mechanism не менять. CLI scan должен оставаться доступным; изменение статусов синхронизировать с локальным шаблоном и тестами, не выдавать его за уже обновлённый scheduler.
- Риск: medium. Отдельная correctness/security проверка обязательна для scheduler и radar.
- Зависимости: новые пакеты, базы, универсальный кеш/новый scheduler не нужны.
- Откат: до commit — только точечно убрать собственный diff, сохранив чужие изменения; тестовые данные изолированы. Не применять destructive git commands; не мигрировать живой state.

## Подцели и приёмка

| ID | Результат | Зависимости / волна | Приёмка |
| --- | --- | --- | --- |
| P0 | Согласуемый паспорт и текущая baseline | none / 1 | Work item + snapshot; prechange PASS; approval absent честно отражён |
| G01 | Один договор автономности и пользовательский сценарий приёмки | P0 / 2 | Templates требуют вход/действие/ожидаемый исход/доказательство и границу local/deployed/accepted; safe steps не требуют повторного подтверждения; существующий gate schema остаётся валиден |
| G02 | Радар не теряет неоценённые обновления | G01 / 3 | Significant и evaluate переживают повторный и пустой batch как pending; завершение оценки отдельно и привязано к id/digest; resolved exact repeat не создаёт новое предложение; legacy/corrupt/conflict/capacity/path/atomic tests PASS, без live state changes |
| G03 | Независимые подцели продолжаются при локальном blocker | G01 / 3 | Blocked G02 не запрещает независимый ready G03; зависимые не запускаются; parent pause/block, отсутствие approval, cap, isolation, duplicate prevention остаются закрытыми |
| G04 | Краткий актуальный контекст и адресное использование Graphify | G02,G03 / 4 | CONTEXT ведёт на текущий паспорт, точную границу результата/блокер/следующий шаг; startup reads ограничены и источники проверены; нет копий transcript и записи в чужой portfolio |
| G05 | Проверки и измерения без лишнего повторного исследования | G04 / 5 | ENGINEERING_LOOP задаёт targeted -> configured gates, без дополнительного ручного полного suite в том же состоянии; обязательные release/high-risk проверки сохранены; существующие schema-1 record/summary/compare и bounded pairKey используются без нового кеша/поля-дубликата |
| G06 | Независимо проверенный интегрированный локальный результат | G05 / 6 | Addressed tests, postchange/release, correctness затем simplify review, свежие HRE-005 acceptance evidence, truthful telemetry и пользовательское CLI-demo; AGENTS.md hash неизменен |

Порядок записи: G01 -> G02 -> G03 -> G04 -> G05 -> G06. G02/G03 логически независимы после G01; исследование/ревью допускается параллельно, но primary не допускает двух writers.

## Исполнение и границы измерения

- Реализация: primary, модель текущей задачи; label sol в schema-v1 snapshot — поддерживаемая роль сложной интеграции, не утверждение о фактической модели primary.
- Поддержка: до 2 одновременно read-only subagents: harness_goal_explorer (Terra medium) и harness_goal_verifier (Sol high), фактический fallback записать. Для короткой подзадачи agent не обязателен. Вложенная делегация запрещена.
- Writer workers и дополнительные обычные задачи не предусмотрены. Реестр обновляет только primary.
- Baseline ID: hre005-before-c60a0e0; treatment ID: hre005-autonomous-v1. Назначены до измеряемого исполнения, не являются доказательством наличия пар.
- Metrics: .harness/metrics/hre-005.jsonl, schema 1; только meaningful checkpoints, реальные token counts или оба null. Accepted — проверенный контракт; used/released не выдумывать.
- Экономию модели/денег не обещать. Без сопоставимой реальной baseline/treatment пары — summary и явное «экономия не измерена». Синтетические regression cases не считать пользовательскими задачами.
- Реальный сравнительный пилот 10–20 задач из разных проектов остаётся следующим отдельно определяемым этапом: выборка, права на проекты и бюджет не заданы.
- Учёт дополнительных просьб/ручных вмешательств — краткие проверяемые факты в work item; новые telemetry поля без необходимости не вводить.

## Goal runner state

- Chain ID: HRE-005
- Project root: D:\6 Проекты\Харнес разработка
- Data owner: workspace-owner
- Risk class: medium
- External-side-effect boundary: local only; exclusions выше
- Parent outcome: автономное завершение согласованной локальной цепочки с проверяемым результатом
- Status: awaiting-user-review
- Plan revision: 1
- Approved passport revision: 1
- Approval provenance: текущая задача, сообщение пользователя 2026-09-05 «подтверждаю HRE-005 revision 1»
- Primary/current task ID: 019fca39-7a3e-7a90-a726-a47e3c72dc19, подтверждён native create_goal; новая обычная задача не создавалась
- Checkout/worktree policy: текущий checkout, primary единственный writer
- Commit policy: no-commit
- Integration branch/worktree: codex/hre-004-update-watcher / текущий checkout
- Last accepted commit: baseline c60a0e0; HRE-005 checkpoint отсутствует
- Current laziness-ladder rung: 2, reuse stdlib/существующих механизмов; для сценарной документации простая правка существующих шаблонов
- Rejected lower rungs: ничего не делать сохраняет воспроизведённые дефекты; новый framework/cache не нужен
- Retained exceptions / ponytail triggers: текущие bounded лимиты сохраняются; новые исключения пока отсутствуют
- Current verified subgoal: G06; локальная интеграция принята независимым verifier
- Next minimal slice and acceptance check: обязательных локальных шагов HRE-005 не осталось; review пользователя. Публикация/активная automation/реальный сравнительный пилот отдельно не разрешены
- Executable plan snapshot: .harness/work/hre-005.passport.json
- Last validated plan snapshot/hash: validator PASS; git hash-object .harness/work/hre-005.passport.json = 29088805ab730b6bddbe690ccab080882c7a5ec5. Все P0/G01–G06 done, агенты done. Старый отказ CHAIN_REVISION относится только к неподтверждённому draft, не текущему запуску.
- Measurement treatment IDs: baseline hre005-before-c60a0e0 | treatment hre005-autonomous-v1
- Metrics path/schema: .harness/metrics/hre-005.jsonl / 1
- Global agent cap: 2
- Active agent count: 0; обе read-only проверки завершены, primary единственный writer
- Delegation depth cap: 1
- Compaction count: как минимум 1 наблюдаемая компактация этой реализации; точный runtime total недоступен. Продолжение из проверенных файлов, без новой обычной задачи
- Context threshold: 45% только если runtime показывает; successor creation не разрешено
- Standing chain authorization: approved
- Standing authorization scope: bounded continuation
- Archive policy: final-explicit-command

## Agent registry

| Agent/task | Parent | Subgoal | Role | Model/effort | Ownership | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| /root/hre005_plan_check | primary | P0 | harness_goal_explorer | Terra medium | read-only acceptance/metrics/templates | done | Existing acceptance + schema-1 telemetry sufficient; no new core schema/dependency |
| /root/hre005_verify | primary | G06 (также G01–G03) | harness_goal_verifier | Sol high | read-only correctness, security, acceptance, simplify | done | G01 forward-test PASS; G02 single-writer scope accepted; G03 occupancy regressions corrected and rechecked; final integration and simplify accepted |

## Task chain

| Seq | Task | Purpose | Status | Archive |
| --- | --- | --- | --- | --- |
| 01 | 019fca39-7a3e-7a90-a726-a47e3c72dc19 | HRE-005 parent | awaiting-user-review | keep |

## Решения

- Revision 1, 2026-09-05: встроить просьбу о максимальной автономности в ограниченную standing authorization; сохранять AGENTS.md и запрет внешних действий.
- Не клонировать/обновлять общий Graphify. Его текущая карта используется только как навигация к первичным файлам.
- Не менять модель primary и глобальные настройки доступа. auto_review уже указан в runtime; он не расширяет permissions: https://learn.chatgpt.com/docs/sandboxing/auto-review .
- Особенность текущего validator: approvedPassportRevision обязателен как integer >=1 даже для planning. До реального approval оставить null и зафиксировать отказ, а не выдумывать подтверждение. Исправление validator не добавлено «заодно»; после одобрения поле получит реальную revision 1.

## Журнал проверок

| Дата | Проверка | Результат |
| --- | --- | --- |
| 2026-09-05 | git status --short --branch до планирования | clean, codex/hre-004-update-watcher |
| 2026-09-05 | scripts/Invoke-HarnessGate.ps1 -Stage prechange | PASS; 97 tests in 5.299 s, passport/benchmark/bootstrap/architecture PASS |
| 2026-09-05 | Read-only Graphify query + primary source reads | Выбраны acceptance, radar, planner, context; graph не пересобирался |
| 2026-09-05 | Independent planning audit | Existing acceptance_gate/metrics достаточны; schema expansion не требуется |
| 2026-09-05 | python goal_runner_validator.py check .harness/work/hre-005.passport.json | FAIL CHAIN_REVISION: approvedPassportRevision null до реального approval; других ошибок не выдано, исполнение не разрешено |
| 2026-09-05 | Snapshot parse, git status, AGENTS.md hash | planning/authorization absent; 6 planned implementation subgoals, 0 ready/running, 0 active agents; только 2 новых planning files; baseline hash AGENTS.md сохранён |

## Передача

G01–G06 завершены локально по approval revision 1; fresh acceptance 5/5 PASS, schema-1 telemetry записана и проверена. Настройка активных автоматизаций, commit/push, публикация, глобальная установка и изменения AGENTS.md не выполнялись. Radar остаётся single-writer, scheduler adoption и экономия на реальных задачах не подтверждены. В этой среде acceptance запускается через внешний Windows PowerShell, как указано в финальных доказательствах ниже.

## Execution evidence

- G01: обновлены существующие skill/references/templates/engineering loop. quick_validate PASS; acceptance template принимается существующим validator, новый manual user-scenario не имеет фиктивного evidence. Адресные acceptance tests PASS (16). Primary correctness и simplify: границы доступа сохранены; новый schema/framework не нужен, отдельный forward-test делегирован read-only verifier.
- Execution prechange PASS на одобренном паспорте; warning о двух собственных planning files ожидаем и разрешён. AGENTS baseline не изменён.
- G02 design: минимальная v2 добавляет evaluation metadata к authoritative seen; legacy seen без metadata означает unknown, не evaluated. Никаких живых scan/migration; только изолированные тесты.
- G01 independent forward-test PASS: build/HTTP200 недостаточны для UI, требуется заполненный просмотр; независимая работа продолжается в разрешённых границах. Skill frontmatter валиден.
- G02: до изменения новые tests дали ожидаемый RED (4 failures/5 errors). После реализации 15 radar tests PASS, вместе с classifier 25 PASS. Repeat/empty сохраняют pending; resolve id/digest/outcome/evidence-bound и идемпотентен; legacy empty не пишет; malformed/capacity/atomic replace error не меняют историю. CLI scan/resolve проверены только на уникальных test-state файлах. Primary correctness/simplify: Python stdlib, одна authoritative seen-map плюс evaluation metadata без дублирования digest/source text; живой state не затронут. Independent review будет завершён перед интеграционной приёмкой.
- G02 final independent review: 16 radar tests PASS, включая resolved useful. Принят single-writer контракт; воспроизведённая гонка двух владельцев — сохранённое ограничение, не обещание concurrent safety. Удалён избыточный reclassifiedLegacyCount. Module/template/README требуют проверенной сериализации; активная automation не обновлялась.
- G03: исходный oracle дал RED (4 failures); основной срез 43 planner+validator tests PASS. Независимый verifier нашёл два непокрытых occupancy случая: blocked writer current checkout и running primary named worktree. Одна bounded correction после goal_progress check/record; regression RED до исправления -> 44 tests PASS после. Re-review воспроизвёл оба случая и независимый launch на другом worktree; correctness и simplify приняты.
- G04: устаревший HRE-001 context заменён текущим HRE-005 snapshot с источниками, границей результата и следующим шагом. Primary проверил реальные startup pointers, согласованность с current passport/git; другой portfolio/graphs/sessions не переписывались. Новых context engines нет.
- G05: существующий ENGINEERING_LOOP описывает адресную проверку -> configured gates без дополнительного ручного full suite в неизменном состоянии. Release/high-risk и fresh evidence не отменены. Architecture CLI fixture теперь использует уникальный state и проверяет pending -> repeat -> resolve -> quiet; PASS. Существующие schema-1 metrics и pairKey сохранены, новая схема/кеш не нужны. README исправлен: configured checks имеют тестовые side effects, стек не угадывается.
- G06 full postchange: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Invoke-HarnessGate.ps1 -Stage postchange -RunFullChecks -Strict PASS; 109 tests / 5.725 s. Benchmark, passport, bootstrap, architecture lifecycle и installer/uninstaller в изолированном TEMP PASS. Установщик не запускался на глобальных пользовательских путях. Native Goal активна до финальной приёмки; AGENTS diff пуст.

## Финальные доказательства G06

- Независимый verifier принял correctness/security, затем simplify всей интеграции. Единственная кодовая переделка по review: G03 occupancy, RED -> исправление -> 44 tests PASS. Новых пакетов/кеша/второй схемы evidence нет.
- Наблюдаемый локальный сценарий: scripts/Test-GoalRunnerArchitecture.ps1 создал UUID-isolated state и проверил scan pending -> exact repeat pending/changed=false -> resolve no-benefit -> exact repeat no-meaningful-updates. Test cleanup ограничен своими временными файлами; живой radar state не участвовал.
- Planner demo: подготовлен реальный GoalOrchestratorTests passport, G02 blocked, G03 ready с dependsOn G01 и worktree independent. plan_actions(p, 'running') вернул ровно hold/G02 и launch/G03; пары действий проверены assert. Это доказательство результата planner, не фактического запуска дополнительной задачи.
- Первое `python acceptance_gate.py check hre-005` дало release FAIL, остальные 4 критерия PASS. Отдельный installer test PASS. Диагностический повтор release с полным выводом локализовал проблему: у Python -> Windows PowerShell наследовался PSModulePath с bundled PowerShell 7 Modules, из-за чего Get-FileHash не находился в architecture/installer; 109 Python tests при этом PASS (5.668 s).
- Без правки исходников/постоянной среды проверен внешний Windows PowerShell: вложенный PowerShell получил нативный Microsoft.PowerShell.Utility 3.1.0.0 и рабочий Get-FileHash. Verifier независимо подтвердил причину и bounded retry. Совместимость произвольного PS7/Python-child окружения не заявляется.
- Финальная команда: `powershell -NoProfile -Command 'python acceptance_gate.py check hre-005; exit $LASTEXITCODE'` — exit 0. Release strict PASS (24,375 ms), passport PASS (375 ms), AGENTS baseline PASS (328 ms), user-scenario PASS, review PASS.
- После записи evidence выполнено только чтение `stored_evidence_is_fresh` для всех пяти criteria: 5/5 fresh, 5/5 passes=true. Повторный full suite ради статуса не запускался.
- `git -c core.safecrlf=false diff --check` PASS; AGENTS.md SHA-256 совпадает с исходной baseline. Passport hash указан в Goal runner state выше. Изменения остаются локальными.
- Telemetry: `python harness_metrics.py record --file .harness/metrics/hre-005.jsonl --from .harness/runtime/hre005-final-event.json` и `summary` PASS. Один реальный checkpoint, durationMs=2497205 от create_goal до завершённой приёмки; attempts=2 означает два acceptance check, checksPassed=5 итоговых критериев, checksFailed=1 первый отказ release. Отдельный диагностический release не считается третьей приёмкой; история его отказа сохранена выше.
- Метрики: reworkCount=1 — correction G03; accepted=true означает технически проверенный контракт, не одобрение результата пользователем. released=false, used=false, actual input/output tokens и модель/effort null. escapedDefects=0 означает отсутствие наблюдённых после приёмки дефектов, не доказательство их невозможности. Реальной baseline/treatment пары нет; экономия не измерена.
- Оставшиеся ограничения: single-writer radar; активный scheduler/global skill не обновлены; другой Graphify/проекты не менялись; реальный сравнительный пилот и внешние действия требуют отдельного scope. Обязательных локальных работ по revision 1 не осталось.
