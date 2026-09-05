# Work item: HRE-006 — распространение Harness

## Контракт и разрешение

- Запрос пользователя 2026-09-05: «все сделай обновление смотри Графифай», в ответ на предложенные пять шагов: проверенный выпуск в существующем GitHub, подключение ПК, регистрация проектов, безопасное обновление, фактическая проверка версии.
- Статус: local-core-published (20 current / 31 inventory); оставшиеся проекты и другие ПК требуют решений по конкретным контрактам/подключения. Это новая область после HRE-005; его запрет публикации/других проектов относился к предыдущей реализации. AGENTS.md baseline остаётся неприкосновенным.
- Исход: воспроизводимая доставка проверенной версии Harness в зарегистрированные проекты доступного ПК и пакет подключения других ПК; недоступные машины/конфликты отражать явно, не считать установленными.
- На этом этапе доступны 31 local project в Codex, один host local. Graphify index от 2026-08-31 содержит 26 проектов, sources.local — 15 путей; это навигация, не разрешение и не актуальная инвентаризация.
- Разрешены разработка и тестирование ограниченного updater, точечная установка управляемых файлов в подтверждённые локальные roots, штатная глобальная установка, публикация проверенных собственных изменений в aidzmitry-gif/harnes-codex без force.
- Не разрешены изменения AGENTS.md/CLAUDE.md, конфигов тестов/production, чужого кода, секретов, контекста/паспортов/метрик/живого radar-state других проектов; удаление пользовательских файлов, изменение ACL, неизвестные SSH/админ-доступы, автоматическая миграция, новые обычные задачи/worktrees.
- Sandbox/permissions не обходить. Отказ на защищённой операции — сохранить результат и запросить направление; независимую локальную разработку продолжить.

## План исполнения

1. G01: Graphify и Codex inventory -> проверенные локальные roots, baseline и конфликтные/недоступные цели.
2. G02: stdlib distribution CLI с фиксированным набором файлов, dry-run, version/hash provenance, закрытыми конфликтами, сериализацией/rollback, изолированными тестами.
3. G03: стабильный выпуск/пакет и инструкция подключения ПК; не менять глобальные cap/models/permissions ради распространения.
4. G04: предварительная проверка правил и активности проектов, точечное применение только допустимых целей; версия/хеши плюс безопасный smoke-test, без исполнения чужих профилей.
5. G05: собственный release gate и independent correctness -> simplify; точная публикация/проверка GitHub при доступе, итоговая матрица ПК/проект/статус и ограничения фонового обновления.

## Инварианты и карта воздействия

- Single writer primary; максимум два read-only помощника без потомков. Публикация и установка только после тестов/review.
- Набор shared modules должен оставаться в корне проекта: acceptance_gate.py вычисляет root из __file__. Центральный symlink на Python helper не подходит.
- Новый trust boundary: filesystem registry/manifest. Только точные allowlisted paths, проверка нормализованных roots без reparse traversal, content hashes, неизвестные/изменённые файлы fail-closed, без произвольных команд/URL из manifest.
- Риск высокий: многопроектные записи. Сначала изолированные unit/integration tests, предосмотр, затем безопасная реальная цель. Rollback только собственных managed artifacts, не очистка broad roots.
- Источник release: текущий проверенный HRE-005 плюс минимальные distribution additions. Initial git: c60a0e0, codex/hre-004-update-watcher; существующий dirty diff — собственный HRE-005, сохранить и проверять. Новые неизвестные изменения не публиковать.
- Baseline: hre006-before-c60a0e0-hre005-local; treatment: hre006-managed-distribution-v1. Runtime token counts неизвестны, экономия не заявляется.

## Приёмка

- Изолированный prepared project с собственными AGENTS/config/work/runtime: plan -> apply -> verify -> repeat no-op; защищённые байты неизменны.
- Изменённый managed файл, неизвестный одноимённый файл, ошибочный manifest, path escape, прерванная транзакция, конкурентная установка: отказ без потери исходных данных.
- Реальный статус каждой обнаруженной цели: current/installed/conflict/deferred/unavailable, с доказательством файлов, не только copied=true.
- Старые/недоступные ПК не считать обновлёнными. Фоновое распространение не обещать без реально подключённого/проверенного scheduler.

## Доказательства

- Graphify query expanded: install/global/project/skill/version. Graph нашёл Install-GoalRunner.ps1:L1 и acceptance_gate.py:L150; snapshot содержит старое имя regression test, поэтому HRE-005 проверяется по исходникам.
- Global goal-runner/context-handoff на текущем ПК являются junction на текущий checkout; это доступность инструкций, не установка всего Harness в соседних проектах.
- G01: private registry `.harness/runtime/hre006-projects.json` содержит 31 реально существующий local root; D: подтверждён Fixed. Источник в Graphify для firmware устарел — используется путь из Codex, без правки Graphify. Индекс Graphify не пересобирался.
- Prechange: PASS, 109 tests; dirty HRE-005 явно учтён. Первый distribution test setup в системном TEMP встретил ACL failure; fixture перенесён в собственный ignored UUID workspace без изменения ACL.
- G02: 19 targeted tests PASS / 11.626 s. Включены stdlib CLI, настоящий PowerShell wrapper, строгий registry (duplicate/unknown/typo отказ до первой записи), Unicode, WhatIf, отсутствие idle ack, no-op, rollback и сохранение конкурентных чужих изменений.
- Independent review нашёл registry fail-open и неразличимые статусы; оба исправлены. Второй проход simplify подтверждает fixed allowlist / stdlib / native lock без лишней зависимости. Финальный post-fix verdict ожидается.
- Portability: source core.autocrlf=true, исходные байты CRLF/LF/mixed. Добавлены только 18 точных правил `.gitattributes text eol=lf`, выполнена механическая LF-нормализация payload, manifest regenerated. Git index checkout при autocrlf=true сохраняет manifest (отдельный fixture). Read-only Git objects удаляются только в собственном UUID fixture; ACL не меняются.
- Промежуточный strict release PASS: 127 tests / 16.981 s + validator/benchmark/bootstrap/architecture/installer. После portability test требуется финальный gate.
- Новый preview: 21 planned, 8 deferred, 1 conflict, 1 source-checkout; файлы проектов ещё не менялись. SEO conflict: scripts/Invoke-HarnessGate.ps1 и templates/work-item.md. Активные microchips.by/CRM ERP, вложенные roots и проекты с отдельным интеграционным контрактом отложены, не объявлены обновлёнными.
- Release ID 2026.09.05-hre006.1, 18 payload files, bundle SHA-256 d88bc538bffe252f73a726c454480718bdd34671a25cca877bed7bdf8cf11dbf. До фактической публикации это локальный проверенный пакет, не выпущенный remote release.

## Фактический rollout и оставшиеся границы

- G03: offline пакет и docs/DISTRIBUTION.md готовы. Global goal-runner/context-handoff текущего ПК уже доступны через существующие junctions, их installer/config не менялись. Источник GitHub проверен: remote branch c60a0e0, целевой tag отсутствует перед публикацией; force не требуется.
- G04 pilot: 3 Защита компьютера — installed18 -> повтор current/changed=false; verify против source PASS; копия validator проверила поставленный example PASS, acceptance_gate --help PASS. Это проверка tools, не пользовательских задач.
- После зелёного пилота получено штатное require_escalated разрешение на точный local registry. Итог 31: 19 current (pilot включён), 10 deferred, 1 SEO conflict, 1 source-checkout. Смешанный результат wrapper намеренно nonzero; не считать 31 успешной установкой.
- 19/19 local copies: точная release receipt, 18 SHA-256 совпадают с source, локальный validator-example smoke PASS. Independent /root/fleet_verify отдельно перепроверил все 19 receipts/18 hashes и отсутствие locks; итог correctness и simplify принят.
- Protected proof: primary сравнил 155 существований/хешей AGENTS.md, CLAUDE.md, harness.config.json, CONTEXT.md, radar-state по registry: 0 изменений. Before/after сохранены только в ignored .harness/runtime/hre006-protected-paths.json; персональные пути не публикуются. Удалены только два UUID собственных упавших Git-fixtures, не пользовательские данные.
- Все 19 имеют profileConfigured=false и projectAcceptance=not-run. Core доступен, но workflow adoption не заявляется. Ни одна прикладная тестовая команда/production-задача другого проекта не запускалась. Глобальный skill доступен текущему пользователю, не всем компьютерам.
- Deferred: 2 active projects; 2 nested roots; Graphify pull-first workflow; 3 custom integration workflows; 1 incomplete Git inventory из-за denied test directories; 1 invalid .git. Точные причины и names/paths только в private registry/report. SEO: отличающиеся gate и work-item template сохранены без merge.
- Other PCs: нет подключённого host/access, значит недоступны для установки. Следующий измеримый шаг — подключить ПК, получить тот же проверенный tag в чистую локальную папку и выполнить preview по его собственному registry. Не переносить auth/config/state/секреты с этого ПК.
- Автоматическое получение/применение будущих релизов не создано: нужен отдельно проверенный trusted source, scheduler и idle gate. Этот CLI не обещает фонового автообновления.
- G05: финальный strict release и source acceptance перед точным staging/commit/push; результат публикации записать отдельно по фактическому remote SHA. Полное распространение на все ПК и внедрение project profiles остаются невыполненными внешними/интеграционными частями, не скрытым done.

## Публикация и финальная проверка 2026-09-05

- Strict release PASS: suite 128 tests + validator, prepared benchmark, bootstrap, architecture и isolated installer. Техническая приёмка HRE-006 5/5 PASS и stored freshness 5/5 true после commit; HRE-005 checkpoint остаётся историческим.
- В commit вошли ровно 26 проверенных source/evidence файлов HRE-005/HRE-006. Private registry, rollout report, protected snapshots, runtime, Graphify и AGENTS.md исключены. Staged diff-check и secret-marker check PASS; все 18 staged/committed Git blobs совпали с raw-byte release manifest.
- Release commit: 7fb53b48061d91af8bc81c7f551755ca3419fb81. Atomic non-force push прошёл в существующую ветку codex/hre-004-update-watcher и новый annotated tag harness-v2026.09.05-hre006.1. `git ls-remote` независимо подтвердил этот SHA и для ветки, и для dereferenced tag. Main не обновлялся; на другом ПК нужно брать именно этот tag, не предполагать свежесть default branch.
- G01–G03 и локальная разрешённая G04/G05 завершены. 19 current core installations не равны 19 принятым бизнес-сценариям. Другие ПК, десять deferred проектов, SEO merge и project profiles остаются явно непокрытыми; будущего фонового автообновления нет.

## Дополнительная проверка deferred после публикации

- Graphify: фактический main checkout оказался clean, обязательный `git pull --ff-only origin main` вернул Already up to date. Установка того же опубликованного payload разрешена штатно и завершена; 18 source-bound hashes, receipt, повторный read-only plan и validator-example PASS. Генераторы/конфигурация портфеля/графы/заметки не менялись; rebuild не потребовался. Итоговая матрица: 20 current, 9 deferred, 1 SEO conflict, 1 source = 31.
- Open Design: независимый полный read AGENTS подтвердил TypeScript-first для новых owned modules/scripts. Python control-plane требует явного исключения владельца; AGENTS не редактировался.
- CRM Логолэнд / microchips-next-site: полный read инструкций подтвердил fresh-task после compaction и own-branch/PR или git-only integration. Проверены текущие ветки security-hardening/readiness-80-loop с 13/499 существующими изменениями. Новая задача/перенос или project PR не создавались без отдельного разрешения; чужую ветку не присваиваем.
- Востановление акб: прямое требование `graphify update .` после code change означает дополнительную запись в индекс другого проекта, которой offline delivery не занимается. Нужен согласованный slice core+index, а не половинная установка.
- ТЕндер QWEN: `.git` — обычный пустой каталог, 0 entries, HEAD отсутствует. Это ломает evidence fingerprint (git-state unavailable вместо non-Git fallback). Ни удаление маркера, ни git init не выполнялись без решения владельца.
- Таким образом причины оставшихся deferred подтверждены чтением/наблюдением, а не общим предположением «нужна проверка». Active-задачи и denied Git inventory также остались нетронутыми.
