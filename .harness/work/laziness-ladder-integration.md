# Work item: laziness-ladder-integration

## Цель

- Проблема: Harness требует минимального среза, но не содержит точной «лестницы лени» из существующих Claude-проектов и не применяет её отдельным проходом code review.
- Результат: каждое изменение выбирает первую достаточную ступень YAGNI → stdlib → native platform → existing dependency → one line → minimum working code; после correctness-review выполняется отдельный simplify-review.
- Не входит: снижение требований безопасности, данных, доступности, явно запрошенного поведения; создание отдельной тяжёлой системы ревью; автоматическое изменение других проектов.

## Контракт и доказательства до правки

- Наблюдения: точный канон найден в `CRM логопидической студии ЛОГОЛЭНД/AGENTS.md` и `CRM ERP/Сlaude CRM - проект/CLAUDE.md`; Graphify указывает на `acceptance_gate.py` и `Invoke-HarnessGate.ps1` как точки доказательств.
- Гипотеза: один короткий reference плюс обязательные ссылки из AGENTS, engineering loop, Goal Runner и worker/verifier ролей обеспечат единое поведение без раздувания контекста.
- Оракул: статический validator проверяет все шесть ступеней, safety carve-outs, `ponytail:` и двухпроходный review; skills/TOML валидны; forward-test выбирает более низкую достаточную ступень и не упрощает trust boundary.
- Инварианты: correctness и safety проверяются до simplify; новая зависимость не добавляется ради нескольких строк; намеренное упрощение имеет измеримый потолок и путь апгрейда; локальные инструкции проекта сильнее общего канона.

## Карта воздействия

- Компоненты: `AGENTS.md`, `docs/ENGINEERING_LOOP.md`, Goal Runner skill/references, worker/verifier TOML, architecture validator, README/ADOPTION.
- Потребители: главный оркестратор, worker, verifier и все задачи проектов, подключающих Harness.
- Данные/миграции: нет.
- Безопасность: нельзя применять лестницу для удаления валидации на границах доверия, защиты от потери данных, security, accessibility или обязательного поведения.
- Внешние зависимости: нет.
- Риск: средний — workflow-инструкция влияет на будущие кодовые изменения.
- Откат: удалить новый reference и связанные короткие ссылки/проверки; глобальные role-файлы повторно синхронизировать installer-ом.

## План минимальных срезов

1. [x] Зафиксировать канон лестницы и двухпроходный code review.
2. [x] Подключить его к общему loop, Goal Runner и ролям.
3. [x] Добавить детерминированную проверку и forward-test.
4. [x] Синхронизировать глобальные роли и закрыть acceptance/gates.

## Журнал проверок

| Время | Проверка | Результат | Вывод |
| --- | --- | --- | --- |
| 2026-08-03 | Graphify query: `acceptance check gate test` | `acceptance_gate.py` и `Invoke-HarnessGate.ps1` — точки доказательств | Встроить статический контракт в существующий validator, не создавать новый gate |
| 2026-08-03 | Поиск точного канона в `D:\6 Проекты` | Найдены совпадающие 6 ступеней и review `code-review → simplify` | Переиспользовать существующую формулировку, не изобретать другую лестницу |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage prechange` | PASS; no config/no checks warnings | Продолжать с адресными проверками |
| 2026-08-03 | Forward-test: date picker | Выбрана ступень 3, native `<input type=date>`; новая JS dependency отклонена | Лестница останавливает реализацию на первом достаточном уровне |
| 2026-08-03 | Forward-test: auth/validator diff review | P0 client-side authorization; затем P2 speculative interface/factory/config | Correctness-pass предшествует simplify и сохраняет safety floor |
| 2026-08-03 | Architecture/installer/skill tests | PASS | Все 6 ступеней, safety carve-outs, ponytail и роли проверены детерминированно |
| 2026-08-03 | Независимая read-only review | P0/High нет | Канон корректно применяется к выполнению и code review |
| 2026-08-03 | Глобальная синхронизация | manifest hashes и source role hashes PASS | Worker/verifier получили новый контракт |
| 2026-08-03 | Postchange gate | PASS; root no-git/no configured checks warnings | Остаточное ограничение зафиксировано |

## Передача

- Что изменено: добавлен единый канон лестницы лени, обязательный выбор ступени в task packet/state/report и двухпроходный correctness→simplify review в общем loop, Goal Runner и ролях.
- Доказательства: два независимых forward-test, architecture/installer/skill validation, независимая review P0/High=0, global manifest/source hashes и postchange gate PASS.
- Остаточный риск / ограничения: корень Harness не является git-репозиторием, поэтому diff/commit недоступны; конкретные проекты могут иметь более строгие локальные исключения и сохраняют приоритет.
