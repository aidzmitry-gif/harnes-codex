# HRE-009 — Единая свежесть acceptance evidence

## Контракт

- Разрешение: пользовательское «перепроверь и улучши реально» от 2026-09-23; локальная правка и проверка.
- Проблема 1: `harness_metrics.acceptance_progress` считает PASS по `passes`, непустому evidence и fingerprint, не проверяя `definitionDigest`. Поэтому отчёт может показать 100% при изменённой команде, хотя `acceptance_gate.status` и Goal unlock отказывают.
- Проблема 2: `evidence_freshness` проверяет digest только для command. Воспроизведено без записи: изменение `description` у manual и переключение command в manual сохраняют `(True, 'fresh stored acceptance evidence')`.
- Проблема 3: при недоступном fingerprint `evaluate` может сообщить PASS и `prove` записать ручной PASS, хотя последующий `status` считает их stale.
- Исход: Goal unlock, `status`, `check` и отчёт задачи одинаково отвергают доказательство изменённого критерия; недоступный fingerprint не даёт ложного PASS; повторное выполнение command или ручное `prove` возвращает свежий PASS.
- Сценарий: сохранённый PASS → изменение `id`, `kind`, `description` или параметра команды без повторной проверки → `status` FAIL, отчёт показывает меньше 100%, Goal unlock закрыт → `reverify`/`prove` создают новое evidence.

## Discovery и воздействие

- Владелец: `acceptance_gate.py`; потребители: `goal_runner_validator.py`, `goal_progress.py`, `harness_metrics.py`.
- Graphify указал функции `fingerprint`, `stored_evidence_is_fresh`, валидатор и метрики; текущий код подтвердил прямой обход общей проверки в `harness_metrics.acceptance_progress`.
- Данные: schemaVersion 2 и формат ledger сохраняются. Старые command/manual записи без нового digest становятся stale до `reverify`/`prove`; массовой миграции нет. Из 12 локальных gate-файлов только один manual-критерий сейчас имеет совпадающий проектный fingerprint: `hre-008.../review`.
- Безопасность: не меняются права, секреты, сеть и исполнение недоверенных команд. Критерии по-прежнему считаются доверенной локальной конфигурацией; SHA-256 не защищает от намеренного редактирования ledger и не равен независимой аттестации.
- Риск: средний — меняется совместимость старых evidence и отчётный процент; безопасное поведение fail-closed.
- Откат: вернуть только новые hunks `acceptance_gate.py`, `harness_metrics.py`, тестов и README; исходную грязную рабочую копию сохранить.

## Минимальный срез

- Лестница лени: переиспользовать `acceptance_gate.evidence_freshness` в метриках и существующий SHA-256/JSON для digest обоих типов критериев. Новых реестров, зависимостей или фоновых процессов нет.
- Оракул: регрессионные тесты сначала красные на обоих ложных PASS; после правки адресные тесты, postchange и release gates, CLI `status`/`reverify` для HRE-009.
- Граница: не редактировать AGENTS.md, другие acceptance-файлы и чужие изменения; не публиковать и не устанавливать в другие проекты.

## Проверки

- [x] Регрессионные тесты сначала были красными на обоих ложных PASS; после правки 28 адресных тестов PASS (2.910 с), 5 benchmark-тестов PASS (0.281 с).
- [x] Метрики, status и Goal unlock используют общую проверку digest/fingerprint; отдельный Goal unlock тест PASS.
- [x] Старое manual evidence требует нового `prove`, старое command evidence — `reverify` (целевые тесты PASS).
- [x] Недоступный fingerprint закрывает `check` до запуска команды и запрещает запись manual PASS (целевые тесты PASS).
- [x] Объявленный 38-тестовый acceptance command и полный release gate PASS вне ограниченного sandbox 2026-09-23. В sandbox полный suite ранее дал 7 failures/14 errors на ACL системного и проектного Temp; исходники для обхода не менялись.
- [x] Correctness-review, затем simplify-review: единая `evidence_freshness` переиспользована в метриках; один digest на два типа критериев, старый command helper сохранён для совместимости; новых зависимостей нет. `acceptance_gate.py status hre-009-acceptance-truth`: 2/2 свежих PASS.

## Результат

- Локально проверено; публикации нет. Токены, `failedAttempts` и реальная экономия времени: нет полной телеметрии; гипотеза о снижении переделок не измерена. Предыдущий отказ auto-review был временным, проверка выполнена штатно после восстановления доступа.
