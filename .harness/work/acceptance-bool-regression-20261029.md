# Work item: acceptance-bool-regression-20261029

## Контракт

- Разрешение: «Продолжай» после ограниченного пилота тестов acceptance gate. Локальное усиление найденного теста; без AGENTS.md, commit, push и изменений других проектов.
- Исход: существующий тест отвергает `passes: 1` и `passes: "false"` при валидных definitionDigest, evidence и fingerprint — именно из-за типа passes, а не повреждённого описания критерия.
- Не входит: изменение production-кода, политик, релиза, моделей, зависимостей или внедрение mutation framework.
- Корень/ветка: managed worktree terra-erp-harness, codex/gpt61-terra-harness; HEAD 1fe22aa0694cce1b9d7e1ba6cb967fdde5a38761; исходное дерево чистое.
- Startup pointers: tests/test_acceptance_gate.py; acceptance_gate.py; docs/ENGINEERING_LOOP.md; harness.config.json; .agents/skills/goal-runner/references/laziness-ladder.md.
- Старый CONTEXT.md относится к HRE-006; не является текущей приёмкой этой задачи и не переписывается.

## Наблюдения и гипотеза

- Предыдущий read-only пилот обнаружил слабую подготовку test_non_boolean_passes_never_opens_stored_evidence: нет definitionDigest, поэтому evaluate может отвергать пример до проверки passes.
- Runtime evidence_freshness и evaluate уже используют строгое сравнение с True. Дефект production-кода не найден.
- Потребители: stored_evidence_is_fresh читает evidence_freshness; evaluate проверяет manual; status использует ту же freshness-функцию. Командный evaluate не запускается в целевом тесте.
- Гипотеза: валидный положительный контроль и оба отрицательных значения в существующем тесте позволят обнаружить ослабление строгого passes в обеих функциях.
- Переиспользование: существующие unittest, patch и criterion_definition_digest; первая достаточная ступень лестницы — existing codebase implementation. Ничего не делать недостаточно для наблюдённого пробела проверки evaluate; новая инфраструктура не нужна.

## Воздействие и откат

- Единственный исполняемый изменяемый файл: tests/test_acceptance_gate.py; одна существующая функция теста. Дополнительно эта обязательная рабочая карточка.
- API, данные, auth, права, сеть, migration, release payload: без изменений. Риск низкий: только тестовый fixture/assertions; проверяемая граница доверия не ослабляется.
- Откат: обратный локальный patch только этих строк теста; чужие изменения не затрагивать.
- AGENTS SHA-256 до правки: 9ec07818b94dbdda4700e50fd873b8130c985c070a5ff81b0249065efd43c723.
- acceptance_gate.py SHA-256 до правки: e47c08b535091fbf0c3f4a18c7bd1e291491d364fc612bc13c2efea48c02d8fd.

## Проверки и показатели до запуска

- Точный целевой набор: один test_non_boolean_passes_never_opens_stored_evidence, исходный код и два неэквивалентных in-memory мутанта: M1 truthiness в evidence_freshness; M2 truthiness в manual evaluate. По три запуска до/после правки = 6 выполнений теста; исходные файлы мутациями не меняются.
- Приёмка: baseline проходит; усиленный тест обнаруживает M1 и M2 через реальные assertions. Не считать ожидаемое падение мутанта ошибкой рабочего кода или неудачной попыткой реализации.
- Gates: prechange, postchange, release; configured fastChecks включают 191 unittest-метод и ещё 4 команды; release также fullChecks installer. Не дублировать полный suite отдельной командой.
- Результат: число обнаруженных неэквивалентных ошибок / 2; зелёный контроль исходного кода; production-код и AGENTS неизменны.
- Операции: одна правка существующего теста; системные запуски и времена записать отдельно. Новых действий пользователя для проверки не требуется; активное человеческое время не измеряется.
- Время: измерять каждую проверку отдельно; не приписывать время runner всей задаче. Начало измеряемого этапа 2026-10-29 04:32:23 UTC; ориентация выполнена ранее и в этот интервал не входит.
- Токены: нет runtime-счётчика, input/output unknown; экономию не заявлять. Runtime model: gpt-6.1-sol; effort не раскрыт.
- Review: correctness/контракт/безопасность, затем simplify. Результаты внести после исполнения.

## Результаты

- Prechange: PASS, exit 0, 36.210 s; 191/191 unittest (27.125 s) и остальные 4 fastChecks. Единственное внешнее предупреждение — наша новая рабочая карточка; исходное дерево до неё проверено чистым. Сообщения FAIL/WARN из негативных/bootstrap fixtures не являются падением внешнего gate.
- До правки: исходный тест PASS (0.0028 s); M1 пойман по тексту ошибки (0.0044 s); M2 не обнаружен (0.0017 s). 1/2 мутаций обнаружена этим выбранным тестом, не утверждение о всём suite.
- Правка: добавлены валидный definitionDigest, положительный контроль True и subTest для "false"/1. Строгие отказы проверяются и через stored_evidence_is_fresh, и через manual evaluate.
- После правки: исходный тест PASS (0.0031 s); M1 и M2 оба дают по 2 assertion failures с фактическим ложным True на двух значениях (0.0033 s / 0.0044 s), без runtime errors. 2/2 неэквивалентных мутаций обнаружены этим тестом. Все 6 запланированных целевых выполнений завершены.
- Postchange Strict: PASS, exit 0, 33.912 s; 191/191 unittest (25.846 s) и остальные 4 fastChecks.
- Correctness-review: фикстура валидна до изменения passes; проверка manual evaluate больше не блокируется отсутствующим digest. Исходный код и AGENTS хэшами не изменены; mock load/fingerprint сохраняет локальность. git diff --check PASS.
- Simplify-review: расширена одна существующая функция без helper/dependency/config/production edit; минимальный loop subTest вместо дублирования тестовых тел. Исключений ponytail нет.
- Release Strict: PASS, exit 0, 73.101 s; 191/191 unittest (25.830 s), остальные fastChecks и fullChecks installer lifecycle/legacy upgrade/config-preserving RolesOnly. Установщик проверялся на временных тестовых профилях, не в пользовательских проектах.
- Итог: критерии этого среза выполнены локально. Исходный код проходит; выбранный тест до/после обнаруживает 1/2 → 2/2 заданных мутаций. Это не общий mutation score всего Harness и не A/B качества модели.
- Исполняемые изменения: одна тестовая функция; плюс обязательная рабочая карточка. 6/6 целевых выполнений, 3/3 обязательных gate; новых инфраструктурных зависимостей нет. Неожиданных failedAttempts реализации 0. Постоянный acceptance ledger для этого малого среза не создавался, поэтому процент свежего gate-report задачи не рассчитывается.
- Граница передачи: проверено локально в managed worktree; не закоммичено, не опубликовано, не перенесено в dirty checkout или ERP. AGENTS.md не менялся. Межпроектного или межмодельного выигрыша из этого опыта не следует.
- Активное время пользователя и токены unknown; экономия рабочего времени/токенов не измерена. Ожидаемые красные mutation assertions не считаются failedAttempts реализации.
