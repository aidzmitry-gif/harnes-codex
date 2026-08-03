# Work item: goal-runner-architecture

## Цель

- Проблема: текущий харнес не умеет управлять большой Goal как графом подцелей, распределять более десяти субагентов, проверять понимание делегированных контрактов и продолжать работу через чистые задачи без немедленного архивирования цепочки.
- Ожидаемый исход для пользователя: `$goal-runner` показывает декомпозицию и проверяемые результаты до старта, после одного подтверждения выполняет независимые подцели параллельными волнами, использует до 12 субагентов и экономную маршрутизацию моделей, сохраняет доказательства и поддерживает безопасный chain handoff.
- Не входит в задачу: запуск реальной большой пользовательской Goal; создание более 10 агентов в текущей сессии; публикация, миграции, удаление данных; снятие продуктовых или аккаунтных лимитов Codex; автоматическое архивирование без итоговой команды пользователя.

## Контракт и доказательства до правки

- Наблюдения: корень не является git-репозиторием; Graphify-граф существует; навыки живут в `.agents/skills`; глобальный `config.toml` не содержит `[agents]`; текущая сессия ограничена четырьмя слотами; официальный Codex поддерживает project/global custom agents и `agents.max_concurrent_threads_per_session`.
- Гипотеза: навык `goal-runner`, четыре узкие агентские роли, cap 12, детерминированный валидатор и bounded chain mode дадут воспроизводимую оркестрацию без раздувания главного контекста и без конкурентной записи в один checkout.
- Оракул: статический тест подтверждает TOML, cap ровно 12, обязательные роли и safety-инварианты; изолированный тест доказывает manifest, идемпотентность, отказ при конфликтах/path traversal, rollback и uninstall; `quick_validate.py` принимает оба навыка; harness gates и независимая read-only рецензия проходят.
- Инварианты / совместимость: один писатель на checkout/worktree; оркестратор единственный владелец канонического состояния; параллельность только по DAG-ready подцелям; дочерние агенты не расширяют полномочия; архивирование только после итоговой проверки и явной команды; fork и перенос transcript запрещены.

## Карта воздействия

- Компоненты и потребители: новый `.agents/skills/goal-runner`; существующий `context-handoff`; `.codex/agents` и конфигурация Codex; installer scripts; README/ADOPTION; будущие проекты, подключающие харнес.
- Данные / миграции: Markdown/JSON/TOML состояние Goal и реестр задач; миграций данных нет. Глобальный config изменяется только отдельным установщиком с backup и TOML-проверкой.
- Безопасность / права / секреты: агенты наследуют sandbox; исследователь и verifier read-only; worker пишет только в назначенный worktree; внешние операции и опасные действия сохраняют отдельные approval gates; секреты не переносятся в отчёты.
- Внешние зависимости: текущие task/subagent tools Codex; доступность моделей; продуктовые лимиты; Git worktree для параллельной записи.
- Риск: средний — workflow управляет конкурентными агентами и может создавать задачи, но не выполняет внешние операции сам по себе.
- Откат: удалить новый навык/агентские TOML/installer; восстановить backup глобального config; вернуть `context-handoff` и reminder к предыдущей версии; созданные задачи не удалять.

## План минимальных срезов

1. [x] Проверить графом существующие точки интеграции и выполнить preflight.
2. [x] Создать минимальный валидный `$goal-runner` с DAG, task contract, verifier и глобальным пулом.
3. [x] Добавить четыре custom-agent роли и cap 12 через безопасный installer.
4. [x] Добавить bounded chain mode в `$context-handoff` и delayed archive registry.
5. [x] Проверить skills/config/scripts, выполнить forward-test, postchange и release gates.

## Журнал проверок

| Время | Проверка | Результат | Вывод / следующее действие |
| --- | --- | --- | --- |
| 2026-08-03 | Ориентация: инструкции, структура, git, config | no-git; Graphify есть; `[agents]` отсутствует | Использовать явный file review; создать managed config block |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage prechange` | PASS; предупреждения: no config/no checks | Допустимо; отдельный acceptance oracle будет добавлен |
| 2026-08-03 | Graphify query: harness/gate/acceptance | `acceptance_gate.py` владеет durable evidence; `Invoke-HarnessGate.ps1` — lifecycle gates | Новый статический тест подключить через acceptance gate; навыки/TOML валидировать напрямую |
| 2026-08-03 | Forward tests: декомпозиция Goal, writer conflict, chain handoff | PASS: адаптивный DAG; конфликтующие auth-записи сериализованы; approved handoff сохранил predecessor без архива | Контракты понятны независимым агентам и сохраняют границы |
| 2026-08-03 | Независимая release-рецензия | Найдены и исправлены provenance schema, rollback/dependency, cap, lead sandbox, worker ACK и false-green gate | Добавлены строгая state schema, read-only lead и транзакционные проверки |
| 2026-08-03 | `Test-GoalRunnerArchitecture.ps1` и `Test-GoalRunnerInstaller.ps1` | PASS | Cap ровно 12; четыре роли; идемпотентность, preflight reject, mid-transaction rollback и uninstall доказаны |
| 2026-08-03 | `quick_validate.py`, Python compile, compact hook | PASS для Goal Runner и Context Handoff; reminder payload содержит chain authorization | Навыки и hook синтаксически/структурно валидны |
| 2026-08-03 | Глобальная установка и read-only проверка | PASS: cap 12, один managed block, два junction, четыре совпадающих role-файла | Требуется новая сессия Codex для применения лимита |
| 2026-08-03 | `Invoke-HarnessGate.ps1 -Stage postchange` | PASS; warnings: root no-git, no configured checks | Область проверена явным перечнем файлов и отдельным acceptance oracle |
| 2026-08-03 | Повторная независимая security/release-рецензия | P0/High нет после трёх циклов review/fix | Закрыты scope escalation, compact bypass, destructive role overwrite, mutable-source uninstall и manifest path traversal |
| 2026-08-03 | Глобальная legacy migration | PASS с `-AdoptVerifiedLegacyRoles`; создан `~/.codex/goal-runner-install.json` | Cap 12, четыре точных имени/хеша, оба skill junction и source sync проверены |
| 2026-08-03 | Git checkpoint policy | Primary-only по умолчанию; clean baseline, atomic commit после acceptance, staged diff review, no auto-push | Коммиты дают историю diff, work item сохраняет решения и доказательства; dirty/overlap останавливает checkpoint |
| 2026-08-03 | Acceptance + release | architecture PASS; installer PASS; manual review PASS; release gate PASS | Релизный контракт закрыт |

## Передача

- Что изменено: добавлен `$goal-runner`, четыре ограниченные роли, cap 12, Goal-chain handoff, compact reminder, транзакционные install/uninstall и adoption-документация.
- Доказательства: architecture/installer/manual acceptance PASS; оба skill validator PASS; forward tests и независимая рецензия P0/High=0; глобальные config/junction/manifest/role hashes проверены; postchange и release gates PASS.
- Остаточный риск / ограничения: корень не является git-репозиторием, поэтому автоматический diff scope недоступен; текущая сессия по-прежнему имеет три subagent-слота; фактический запуск более десяти агентов требует новой сессии и зависит от runtime/account limits и безопасной независимости подцелей.
