# Work item: context-handoff-reminder

## Цель

- Проблема: пользователь должен помнить о `$context-handoff` после ручного или автоматического сжатия задачи.
- Ожидаемый исход для пользователя: после compact Codex получает короткое напоминание предложить `$context-handoff`, не выполняя handoff автоматически.
- Не входит в задачу: запись project context, создание/архивирование задач, чтение transcript, проверка процента токенов, scheduled automation.

## Контракт и доказательства до правки

- Наблюдения: глобальный `config.toml` валиден, hooks не отключены, `SessionStart` hooks и context reminder отсутствуют; официальный matcher `^compact$` запускается после compact перед следующим model request.
- Гипотеза: глобальный `SessionStart` command hook с малым `additionalContext` даст своевременное напоминание без фоновых задач и без переноса истории.
- Оракул: hook на входе `SessionStart/source=compact` возвращает валидный JSON с reminder; на других событиях не добавляет контекст; итоговый `config.toml` парсится и содержит ровно один managed block.
- Инварианты / совместимость: не читать transcript; не писать проектные файлы; не создавать и не архивировать задачи; вывод менее 250 токенов; повторная установка идемпотентна.

## Карта воздействия

- Компоненты и потребители: global Codex `config.toml`, hook script навыка `context-handoff`, все будущие локальные задачи Codex после compact.
- Данные / миграции: добавляется один TOML hook block; миграций нет.
- Безопасность / права / секреты: stdin содержит session metadata, но hook использует только event/source и ничего не логирует; резервная копия config создаётся локально и не выводится.
- Внешние зависимости: локальный Python 3.12 из PATH; Codex hooks.
- Риск: средний — ошибка global config может повлиять на запуск всех задач.
- Откат: восстановить `config.toml.bak-context-handoff-reminder` или удалить managed hook block; удалить hook script.

## План минимальных срезов

1. [x] Добавить hook script и проверить JSON-контракт напрямую.
2. [x] Добавить идемпотентный installer с backup и TOML validation.
3. [x] Установить global hook, проверить итог и выполнить harness gates.

## Журнал проверок

| Время | Проверка | Результат | Вывод / следующее действие |
| --- | --- | --- | --- |
| 2026-08-03 | Ориентация global config | TOML valid; 150 строк; reminder отсутствует; hooks enabled | Можно добавить изолированный array-of-tables block |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage prechange` | PASS; warnings: no config/checks | Продолжить с адресными проверками |
| 2026-08-03 | Hook syntax + direct compact/startup inputs | PASS; compact возвращает SessionStart additionalContext, startup не выводит ничего | Hook ограничен нужным событием и не мутирует состояние |
| 2026-08-03 | Installer `-WhatIf` | Первая попытка выявила quoting bug Python `-c`; исправлено, повторный dry-run PASS | Диагностика локализовала проблему до global write |
| 2026-08-03 | Global install | PASS; создан backup; config TOML valid; ровно 1 matcher; timeout=5, context limit=250 | Напоминание установлено без дубликатов |
| 2026-08-03 | Повторный installer | PASS already installed | Идемпотентность подтверждена |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage postchange` | PASS; warnings: no git/configured checks | Перейти к release gate |
| 2026-08-03 | `codex --version` после изменения | Не запущен: Windows вернул Access denied и в sandbox, и escalated | TOML и hook проверены отдельно; для загрузки hook нужен restart/new session |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage release` | PASS; warnings: no git/configured checks | Готово к передаче с ограничением product smoke test |

## Передача

- Что изменено: добавлены hook script, идемпотентный installer, README и глобальный `SessionStart` matcher `^compact$` в `~/.codex/config.toml`.
- Доказательства: прямой JSON test, silent non-compact test, source/candidate/final TOML validation, match count=1, valid preinstall backup, repeated install PASS, harness pre/post gates PASS.
- Остаточный риск / ограничения: текущий процесс Codex уже загрузил старую конфигурацию; нужен restart или новая сессия. `codex.exe` нельзя было запустить из shell из-за Access denied, поэтому product-level smoke test будет фактически выполнен при следующем compact.
