# Подключение harness к проектам

## Принцип

Не копируйте сложный ERP-контур в каждый репозиторий. Подключайте минимальный уровень, который соответствует риску проекта. Локальные `AGENTS.md`, `CLAUDE.md`, CI и правила владельца всегда приоритетнее общего шаблона.

## Уровни

| Уровень | Когда использовать | Состав |
| --- | --- | --- |
| Базовый | новый, личный или изолированный проект | `AGENTS.md`, work item, `Invoke-HarnessGate.ps1`, профиль проекта |
| Проверяемый | API, бизнес-логика, командная работа | базовый + `acceptance_gate.py` и команды тестов в профиле |
| Критичный | деньги, ПДн, права, production, миграции | проверяемый + локальные pre-tool guards, CI, ownership и явный план отката |

## Порядок подключения

Для распространения одной проверенной версии core по уже выбранным проектам
используйте [DISTRIBUTION.md](DISTRIBUTION.md). Он не заменяет перечисленные ниже
проверки локального контракта и не создаёт профиль с выдуманными командами.

1. Убедитесь, что рабочая копия чиста или ваши файлы изолированы в своей ветке/worktree.
2. Прочитайте действующие `AGENTS.md`, `CLAUDE.md`, CI и правила деплоя. Не заменяйте их.
3. Скопируйте `templates/project-profile.example.json` в `harness.config.json` и укажите только безопасные локальные команды.
4. Для нетривиальной задачи создайте work item и выполните prechange gate.
5. Скопируйте acceptance template, замените демонстрационные команды фактическими и создайте durable gate:

   ```powershell
   python .\acceptance_gate.py init <work-item> --from .\my-acceptance.json
   python .\acceptance_gate.py prove <work-item> review --evidence "Reviewed git diff; rollback is commit <hash>."
   python .\acceptance_gate.py check <work-item>
   ```

`check` всегда заново запускает критерии вида `command`, сохраняя фактический exit code как evidence. Ручной критерий проходит только с явным evidence. Не включайте в JSON destructive, сетевые или production-команды.

## Карта текущей рабочей области

- **CRM ERP:** уже критичный контур; не подменять его. Улучшения делайте в канонической копии и отдельно планируйте синхронизацию worktree.
- **SEO Сервис и Логолэнд:** начать с проверяемого уровня, только в чистой ветке и после согласования владельца.
- **Olivia, Arseny, ТЕндер QWEN, microchips.by:** начать с базового уровня и сначала документировать реальные команды проверки.

## Проверка профиля

Профиль — декларация для человека и агента. `Invoke-HarnessGate.ps1` использует те же поля `protectedPaths`, `fastChecks` и `fullChecks`, поэтому его можно настроить без дополнительного инструмента.

## Подключение Goal Runner

Используйте `$goal-runner` для большой цели с несколькими проверяемыми результатами, а не для короткой последовательной правки.

1. Выполните `scripts/Install-GoalRunner.ps1 -WhatIf` и проверьте целевые глобальные пути.
2. Установите фиксированный cap командой `scripts/Install-GoalRunner.ps1 -MaxConcurrentSubagents 12`, затем перезапустите Codex. Installer также подключит общий Context Handoff, создаст manifest хешей установленной версии, откажется перезаписывать чужие role-файлы и откатит все свои изменения при частичном сбое.
3. Запустите `$goal-runner <наблюдаемый результат>`.
4. До подтверждения проверьте Goal passport: все подцели, DAG-волны, модели, ownership, acceptance и ожидаемые handoff.
5. Разрешайте параллельную запись только в независимых worktree. В одном checkout используйте одного worker.
6. После проверки родительского результата отдельной командой архивируйте зарегистрированный chain ID.
7. Для git-проекта выберите commit policy в Goal passport. Рекомендуемый режим — primary-only: один атомарный commit после acceptance каждой подцели, хеш записывается в work item, push остаётся отдельным действием пользователя.
8. Для каждой write-подцели зафиксируйте первую достаточную ступень лестницы лени и причины отказа от нижних. Перед acceptance выполните correctness-review, затем отдельный simplify-review; не используйте упрощение против safety floor.

### Измеряемый workflow

В Goal work item остаётся единственный журнал решений. Рядом создайте его машиночитаемую проекцию `.harness/work/<chain>.passport.json`, затем запускайте:

```powershell
python .\goal_runner_validator.py check .harness\work\<chain>.passport.json
```

Проверка обязательна до каждой записи worker и после изменения плана, authorization или agent registry. До измеряемого запуска назначьте короткие ID baseline/treatment. На контрольных точках запуска или принятой подцели запишите только структурированное событие с реальными runtime-токенами либо парой `null`; не передавайте transcript, свободный текст или оценочные токены. Сравнение запускайте только при наличии валидных пар:

```powershell
python .\harness_metrics.py record --file .harness\metrics\<chain>.jsonl --from .harness\work\<event>.json
python .\harness_metrics.py compare --file .harness\metrics\<chain>.jsonl --baseline baseline --treatment treatment
python .\harness_benchmark.py --fixture .\tests\fixtures\hre-001-benchmark.json
```

Последняя команда — детерминированное regression evidence качества относительно общего oracle; она не доказывает экономию токенов в реальной разработке и не заявляет статистическую значимость. При `$context-handoff` передавайте только treatment ID, path/schema metrics, последний проверенный passport/hash и verified boundary; в новой задаче снова валидируйте passport. Не копируйте telemetry rows, чаты, transcript или выдуманные токены.

Для удаления выполните `scripts/Uninstall-GoalRunner.ps1 -WhatIf`, затем ту же команду без `-WhatIf`. Удаляются только managed `[agents]`, Goal Runner junction и четыре неизменённых role-файла; общий Context Handoff сохраняется.

Не оценивайте готовность по числу запущенных агентов. Пул до 12 нужен для независимой работы; оркестратор обязан уменьшать волну, если зависимости, доступный runtime или изоляция не позволяют безопасную параллельность.

## Автономный радар обновлений OpenAI

Сначала проверьте локальный контракт вручную:

```powershell
python .\update_radar.py scan .\templates\update-batch.example.json --state .harness\runtime\update-radar-state.json
```

Затем создайте в ChatGPT desktop Scheduled Task для этого локального проекта и используйте `templates/update-radar-task.md` как каноническую инструкцию. Рекомендуемый режим — ежедневный локальный запуск в 09:00 по часовому поясу пользователя, report-only, с уведомлением о каждом результате. Компьютер и приложение должны быть запущены, когда задаче нужны локальные файлы; это ограничение подтверждено [официальной документацией OpenAI Scheduled Tasks](https://learn.chatgpt.com/docs/automations).

Runtime-файлы `.harness/runtime/update-radar-batch.json` и `.harness/runtime/update-radar-state.json` игнорируются Git. Они являются локальным журналом дедупликации, а не acceptance evidence. Не переносите их между проектами: соседний репозиторий должен подключать и проверять Harness отдельно.
