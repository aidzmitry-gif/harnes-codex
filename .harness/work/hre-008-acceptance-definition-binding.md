# HRE-008 — Привязка acceptance evidence к определению проверки

## Цель

- Проблема: `acceptance_gate.py` исключает `.harness/acceptance/` из fingerprint проекта. Поэтому сохранённый PASS командного критерия может выглядеть свежим после изменения самой команды: fingerprint проекта остаётся прежним.
- Ожидаемый исход для пользователя: статус показывает только актуальное evidence; изменение команды, таймаута, `cwd` или ожидаемого маркера делает старый PASS недействительным, а повторная проверка создаёт новое evidence.
- Не входит в задачу: установка `unlazy`, новый оркестратор/ledger, sandbox команд, сетевые действия, изменение уже существующих acceptance-файлов, установка hook, массовая миграция и заявления об экономии времени/токенов.

## Пользовательский сценарий приёмки

- Безопасные подготовленные входы / заполненный пример: локальный `.harness/acceptance/hre-008-acceptance-definition-binding.json` и unit-тесты с временными ledger-файлами.
- Действие пользователя или воспроизводимая команда: `python acceptance_gate.py status hre-008-acceptance-definition-binding`, затем `python acceptance_gate.py reverify hre-008-acceptance-definition-binding`.
- Ожидаемый наблюдаемый результат: `status` не исполняет acceptance-критерии и не меняет ledger; устаревший command evidence отображается как FAIL. `reverify` выполняет проверку, требует exit code 0 и заданный `expect` marker, затем сохраняет fingerprint и SHA-256 определения команды.
- Свежие доказательства: `python -m unittest tests.test_acceptance_gate -v`, postchange/release Harness gates и acceptance JSON этой карточки.
- Граница передачи: проверено локально; публикация и установка в другие проекты не входят.

## Автономность и продолжение

- Одобренный объём и источник разрешения: пользовательское «хорошо делай» от 2026-09-23 — применить предложенный минимальный срез из анализа `unlazy`.
- Самостоятельные шаги: адресные тесты, совместимый кодовый срез, полный локальный release gate, correctness-review и simplify-review.
- Блокер: отсутствует; существующие незакоммиченные изменения сохраняются. В `acceptance_gate.py` уже есть отдельная правка поддержки `repository_root`; она не заменяется.
- Следующая независимая безопасная работа: отсутствует.

## Контракт и воздействие

- Затронуты: `acceptance_gate.py`, его unit-тесты, шаблон acceptance и краткий CLI-раздел README.
- Повторные потребители: `goal_runner_validator.py` через `stored_evidence_is_fresh`; он должен закрывать unlock при изменённом или отсутствующем digest.
- Инварианты: старые ledger читаются; их command evidence без digest становится stale до повторного запуска; manual evidence сохраняет существующие правила свежести; `status` не исполняет команды и не пишет; `check` остаётся совместимым и по-прежнему запускает команды.
- Граница безопасности: `CHECK` остаётся доверенной локальной командой с полномочиями текущего процесса. Новый `cwd` — только существующая директория внутри корня проекта без выхода через symlink. `expect` — ограниченная точная строка отдельной строки вывода; PASS требует одновременно нулевой exit code и совпадение маркера.
- Риск: средний, меняется acceptance-контракт и данные evidence; внешних зависимостей и миграций нет.
- Минимальный эксперимент: регрессионно доказать, что изменение каждого поля определения отклоняет старое evidence, свежий запуск проходит только с маркером, а `status` остаётся read-only.
- Откат: отменить только собственные hunks и файлы HRE-008 после проверки diff; существующие незакоммиченные изменения оставить нетронутыми.

## Лестница лени и повторное использование

- Выбранная ступень: изменить существующие `acceptance_gate.py` и тесты; reuse существующий SHA-256, проектный fingerprint и durable acceptance JSON.
- Проверено: локальная функция fingerprint намеренно исключает `.harness/acceptance/`, а `stored_evidence_is_fresh` используется валидатором Goal для unlock. Новая система доказательств или runtime dependency не нужна.
- Отвергнутые нижние/верхние варианты: только перепроверять изменение файлов недостаточно, поскольку acceptance JSON исключён из fingerprint; внедрение всей `unlazy` добавило бы второй workflow и Node-слой.

## Наблюдения и ход выполнения

- 2026-09-23: рабочая копия уже содержит несвязанные изменения. Текущая правка `acceptance_gate.py` ограничена параметром `repository_root` в fingerprint helpers; этот участок сохраняется без переписывания.
- До изменения: `stored_evidence_is_fresh` сравнивает pass/evidence и fingerprint проекта, но не текущий command definition; критерий команд выполняется в `evaluate`.
- До изменения: автоматический evidence сохраняет exit code и строку вывода, но не подтверждает заданный ожидаемый маркер.
- Prechange: ограниченный запуск выявил 7 failures и 14 errors в полной Python suite; затронутые `harness_json`/metrics тесты не могли создать/очистить временные каталоги в sandbox. Причина локализована как ограничение файловых прав запуска; сам `acceptance_gate` тестовый набор затем прошёл вне sandbox.
- Целевые тесты: `python -m unittest tests.test_acceptance_gate -v` — PASS, 23 теста, 3.050 s.
- Postchange: `Invoke-HarnessGate.ps1 -Stage postchange` — PASS; 162 Python теста, 18.729 s; passport, benchmark, bootstrap и architecture проверки PASS.
- Release: `Invoke-HarnessGate.ps1 -Stage release` — PASS; 162 Python теста, 19.914 s; bootstrap, architecture и изолированные installer install/uninstall тесты PASS.
- Финальный `python acceptance_gate.py reverify hre-008-acceptance-definition-binding` после записи manual review — exit 0: command criterion PASS, `expect` marker matched, manual review PASS. Следующий `status` показал оба критерия fresh.
- Correctness-review: PASS — exit code и полный отдельный output line обязательны вместе; digest покрывает command/timeout/cwd/expect; `cwd` остаётся в корне даже через symlink; status не запускает критерии и не пишет ledger; старый command evidence без digest закрывает unlock.
- Simplify-review: PASS — переиспользуются stdlib SHA-256, существующий fingerprint, acceptance JSON и CLI; новых зависимостей, ledger, hook, installer или workflow нет. Предсуществующая правка `repository_root` в fingerprint helper сохранена.
- Финальная проверка `python acceptance_gate.py status hre-008-acceptance-definition-binding`: оба критерия PASS и fresh; `git diff --check` по затронутым tracked-файлам — PASS.

## Приёмка

- [x] Изменения команды, таймаута, `cwd` и `expect` дают разные SHA-256 definition digest.
- [x] `status` read-only и отказывает для отсутствующего/устаревшего command evidence и устаревшего manual evidence.
- [x] `reverify` запускает runnable criteria; с объявленным `expect` успех требует exit code 0 и точной строки marker.
- [x] `stored_evidence_is_fresh` закрывает unlock при старом/отсутствующем command definition digest.
- [x] Адресный набор, postchange gate и release gate PASS.
- [x] Correctness-review и отдельный simplify-review выполнены.

## Решение и передача

- Результат: локальная реализация завершена и проверена; не коммитилась и не публиковалась.
- Ограничения: успешная локальная проверка не является публикацией или пользовательской приёмкой.
