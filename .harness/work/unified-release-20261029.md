# Единый локальный релиз Harness — 2026-10-29

## Цель и разрешение

Пользователь подтвердил «продолжай» после плана объединить проверенные CLI, переносимость и durable radar в существующей изолированной копии. Основной checkout `D:/6 Проекты/Харнес разработка` — только источник для адресного чтения; его dirty edits не переносятся вслепую и не изменяются. Рабочая ветка `codex/gpt61-terra-harness`, исходный HEAD `1fe22aa0694cce1b9d7e1ba6cb967fdde5a38761`.

Исход для пользователя: один локально устанавливаемый комплект включает готовый `session-summary`, его зависимости и радар с сохранением evidence/blocker/recheckWhen. Пока это локальный кандидат, не опубликованный релиз и не установка в пользовательские проекты.

Не входят: AGENTS.md, commit/push/PR/deploy, глобальные роли/config, работающие проекты и scheduler, live radar state, миграция Goal history, отдельный evaluation framework, новые модельные вызовы.

## Контракт и показатели до реализации/проверок

- Применимые стандарты: текущие `AGENTS.md`, `docs/ENGINEERING_LOOP.md`, `docs/DISTRIBUTION.md`, каноническая laziness ladder. Graphify: release_manifest / harness_codex / harness_metrics / tests.test_update_radar; факты проверены по исходникам.
- Результат: M=6 критериев ниже. Приняты только фактически проверенные, blocker не считается PASS. Общий процент acceptance ledger не заявляется.
- Операции: фиксированный комплект 18 → 22 файла; потребитель использует существующий CLI вместо нового парсера. Считаем исполнения адресных тестов и 6 локальных сценариев установки отдельно. Новых GPT запусков — 0; стоимость этого диалога и труд пользователя неизвестны, не ноль.
- Время: длительность каждого gate, адресного набора и локальной установки измеряется отдельно. Это не A/B общей продуктивности и не обещание экономии.
- План до тестов: prechange — существующие 191 unit methods + 4 configured fast checks; целевой набор 133 methods в шести модулях; после интеграции postchange/release — ожидаемые 240 unit methods каждый + 4 fast checks, release дополнительно installer lifecycle. Число проверяется discovery без выполнения до запуска. Отдельный полный suite рядом с gate не запускается.

## Критерии приёмки — M=6

1. Exact22 manifest загружается; свежая установка импортирует все Python helpers из самого проекта без source PYTHONPATH; установленный CLI проходит те же 6 синтетических случаев.
2. Валидный предыдущий exact18 комплект обновляется до exact22; AGENTS/config/user data не изменены.
3. Повтор — no-op; изменённый managed либо новый unmanaged helper блокирует запись без потери данных.
4. Native schema3 дельты/unknown/subsets/checkpoints проходят адресные регрессии и существующий budget guard; schemas1/2 остаются читаемыми.
5. Radar v3 сохраняет candidate/evidence/blocker/recheckWhen, неизменные prerequisites не вызывают повтор; legacy читается без отдельной миграции; реальные runtime state не трогаются.
6. Terra allowlist/dispatch, прежний strict boolean regression и оба AGENTS baseline сохранены; gates и raw-byte Git export true/false проходят.

## Переиспользование и минимальный срез

Первая достаточная ступень — existing codebase implementation. Уже проверены `harness_codex.py`, `harness_metrics.py`, `harness_distribution.py`, `update_radar.py`, тесты sessions/distribution/radar и dependency `harness_instruction_audit.py`. Новый сервис/collector/parser/CLI не создаётся.

Переносятся только native usage/schema3, exact22 distribution+legacy18, `.gitattributes -text`, dependency audit helper, связанный radar template и документация CLI/distribution. Из validator — только разрешение metrics schema3. В ENGINEERING_LOOP добавлено только связанное описание report-only helper (8 строк), не полная новая политика измерений. Не переносятся Goal signatureIndex, evaluation-suite reporting, изменения общего work-item и ослабленные/сокращённые Terra tests из основной копии.

Первопричина разрыва: manifest и distribution fixed list существующей ветки содержат18 файлов и не доставляют готовый CLI/зависимости. Потребители: distribution inspect/apply/verify, Windows wrapper, native usage reader/metrics/budget, radar scan/pending/defer/resolve. Внешние установленные проекты не проверяются и не изменяются.

## Карта воздействия и откат

- Риск средний: файловая установка/rollback, bounded локальный JSON/JSONL, state persistence; сети/секретов/новых зависимостей нет.
- Данные: только disposable test projects и ignored runtime evidence. Никакой живой миграции, удаления истории или изменения чужих паспортов.
- Конкурентность: существующий distribution lock и cooperating importer lock сохраняются; radar по-прежнему требует single writer.
- Уже имеющиеся изменения `tests/test_acceptance_gate.py` и `.harness/work/acceptance-bool-regression-20261029.md` принадлежат предыдущему завершённому срезу и сохраняются byte-identical.
- Откат: точные предшествующие managed bytes сохраняются в ignored snapshot перед реализацией; восстанавливать только собственные пути при отдельной необходимости, без reset/checkout/delete. Live v3 state не откатывается старым reader.

## План

1. Prechange и snapshot текущих payload/защищённых файлов.
2. Перенос выбранных существующих реализаций и регрессий, новый local manifest.
3. Адресные133, postchange, шесть disposable lifecycle сценариев, correctness и simplify review, release.
4. Обновить текущий раздел `.harness/CONTEXT.md` с точными доказательствами и границами.

## Журнал и передача

- До реализации: рабочая копия содержит только прежний boolean regression и его карточку; основная папка не изменяется. Доказательства данного среза: `.harness/runtime/unified-release-20261029/`.
- Prechange PASS: 191/191 unit + 4 fast checks, 35.1788 s; разрешённое предупреждение о прежнем boolean regression и новой карточке. Вложенные fixture WARN не относятся к outer gate. Snapshot exact18 и 35 protected hashes сохранён; исходная папка не изменена.
- Подготовка evidence сначала остановилась на отсутствующем runtime-каталоге; каталог создан штатным узким разрешённым вызовом, до этого код интеграции/тесты не запускались.
- Discovery подтвердил ровно 133 адресных и 240 общих unit methods до исполнения. Из source metrics удалён не относящийся к задаче evaluation framework; Goal index и более слабые source Terra tests не переносились.
- После `-text` два уже изменённых helper оказались CRLF при LF в Git HEAD. Перед проверками их окончания строк приведены к исходному LF, чтобы избежать случайного полного diff; manifest пересчитан. Остальные ранее существовавшие bytes/AGENTS не нормализовались.
- Target PASS: 133/133, 32.3859 s; protected hashes unchanged. Release candidate `2026.10.29-unified.local.1`, exact22, bundle `a42837114f5ecc1cddb7565fafbcfaf747d2a0657f1ba8c6713c0aa04206bf2b`.
- Strict postchange PASS: 240/240 + 4 fast checks, 43.6016 s, protected hashes unchanged.
- Disposable lifecycle PASS: 6/6 in6.9038 s; installed CLI6/6, isolated imports, exact18→22 and6 protected owner files, byte-identical no-op, managed/unmanaged conflicts refuse without writes, installed radar legacy pending is read-only and v3 retains facts/checkpoints/terminal evidence with UTF8 BOM stdin. Unchanged prerequisites0 eligible rechecks, changed1. Fixture root is retained only for evidence; no real project was installed.
- Correctness review: selected diff, exact22/hash validation, trust-boundary counters/paths, legacy18 ownership, cooperating locks, radar single-writer/old-reader limitations and protected baselines checked. No new blocker found. This is primary self-review, not an independent external attestation.
- Separate simplify review: existing implementations reused; removed source's unrelated300+ line evaluation framework, retained only native schema3 additions and one strict validator regression; no Goal-index migration or model/config change. Extra auditor remains because fixed22 and isolated import/dependency coverage require it. No speculative service/dependency/registry added.
- Instruction audit: initial wrapper used Windows backslashes in a repo-relative manifest path and was refused before instruction reads; rerun with `.as_posix()` PASS. Six changed Markdown files covered, no truncation/broken local links;2 duplicate groups are only opening/closing code fences. No audit/parser validation was weakened.
- Strict release PASS: 240/240 + 4 fast checks + isolated installer lifecycle,83.0192 s; all35 protected hashes match, `git diff --check` PASS. The raw-byte Git export/fresh install regression ran for autocrlf=true and false inside distribution tests. No commits were created, including in this worktree; real project deployment was not performed.

## Итог

- M=6/6 criteria in this work item's bounded local contract verified by source/tests/disposable lifecycle; not an independent production acceptance score. Target133/133; postchange/release240/240 each. No extra full-suite run outside required gates.
- Release `2026.10.29-unified.local.1`, exact22, bundle `a42837114f5ecc1cddb7565fafbcfaf747d2a0657f1ba8c6713c0aa04206bf2b`. Installed CLI solves all6 prior fixture cases from another cwd without a generated adapter. Candidate/source files are distinct from source checkout's complete newer experimental features; no claim of blanket migration.
- Time measurements describe these checks only. Dialogue/implementation input/output tokens, human effort, billing and project productivity gain are unknown. Additional native model runs0; no model or reasoning defaults switched.
- Source `D:/6 Проекты/Харнес разработка`, both AGENTS, prior boolean regression/card and config preserved. No live radar migration, scheduler changes, installation into real projects, commit, push, PR or deploy.
- Further rollout requires fresh target instructions/idle/conflict review and the applicable authorization. A receipt proving22 files does not prove project adoption. Private detailed receipts, rollback snapshot and retained temporary fixtures: `.harness/runtime/unified-release-20261029/result.json` and its referenced files.

## Публикация — отдельное разрешение 2026-10-30

- Пользователь: «Сделай коммит и пуш последнего релиза в aidzmitry-gif/harnes-codex. AGENTS.md не меняй». Это отменяет прежнее ограничение commit/push только для данного exact release, не разрешает merge в main, PR/tag, deploy или обновление других проектов.
- До действий: payload exact22 и bundle `a42837114f5ecc1cddb7565fafbcfaf747d2a0657f1ba8c6713c0aa04206bf2b` совпали с проверенным кандидатом; индекс пуст, remote branch равен implementation baseline. В commit входят только22 согласованных изменённых пути: комплект, его docs/context/work cards и регрессии, включая предыдущий boolean test. Ignored runtime/локальные журналы/реестры не публикуются.
- Проверки до публикации: один свежий Strict release gate (240 unit methods +4 fast checks +installer lifecycle), staged payload hashes22/22, отсутствие AGENTS/секретов/посторонних путей в индексе; после push — точное совпадение remote branch SHA с commit и неизменный remote main.
- Модельных вызовов не требуется. Измеряется длительность release gate и операций публикации; расход диалога и экономия продуктивности неизвестны. Итоговый commit определяется Git, а не самоссылкой в тексте этого commit; локальная квитанция — `.harness/runtime/unified-release-20261029/publication-20261030.json`.
- Первый publication gate:240 unit methods прошли, но gate FAIL из-за одного срабатывания heuristic secret scan на synthetic private canary в новом `tests/test_harness_sessions.py`. Реальный credential не найден; значения не выводились. Эта фикстура прежде была untracked и не попадала в Git diff guard, поэтому прежний локальный PASS не доказывал чистоту staged diff. Квитанция первого отказа сохранена отдельно.
- Минимальная подготовительная правка: synthetic chat event содержит тот же private canary без credential-like присваивания, переменная названа `private_event`; приватностные assertions и production-код не изменены, scanner не отключён и не ослаблен. До повторных тестов: один privacy regression и затем полный Strict release240 +4 fast checks +installer; состав22 и bundle payload остаются прежними.
- Повторная проверка: privacy regression1/1 PASS (0.029 s), затем Strict release gate PASS —240/240 +4 fast checks +installer lifecycle,75.2288 s. Все staged payload hashes22/22 и оба AGENTS совпали, secret guard не сработал. Квитанции первого отказа и успешного повтора не перезаписывают друг друга; добавленная после gate строка — только фактический результат, исполняемые файлы/критерии не менялись.
