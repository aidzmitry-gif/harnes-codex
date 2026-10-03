# HRE-012 — измеримые запуски и проверяемый ответ

Статус: **local-verified; revision 1; scoped commit handoff checkpoint**. Пользователь в текущем чате `019fca39-7a3e-7a90-a726-a47e3c72dc19` написал: «коммит и Подтверждаю HRE-012 revision 1». Это разрешает согласованную локальную реализацию и primary-only commit HRE-012; не push, живой model/API-пилот, изменение настроек или перенос чужого baseline.

## Цель

- Проблема: пилот HRE-011 не имел наблюдаемой per-run usage; свободный ответ допускает несовпадение типов; существующий планировщик не учитывает измеряемый бюджет при рекомендации следующего запуска.
- Результат: локально получить безопасную числовую сводку из явно выбранного Codex JSONL; отклонить неверный машинный результат; при включённом бюджете получить `hold` вместо следующего `launch`, если лимит достигнут или доказательств для его проверки недостаточно.
- Не входит: новый фреймворк/оркестратор, модельная миграция, изменение AGENTS.md, глобальных настроек, skills, HRE-011, CONTEXT.md, release manifest; установка, push/PR/deploy, другие проекты, живой вызов модели, API-расходы, чтение auth.json/.env, обход sandbox или управление кнопкой Goal. Commit разрешён отдельно последним сообщением пользователя, только для HRE-012.
- Важная граница: `hold` — запрет следующего запуска в плане Harness, а не принудительное завершение уже работающего GPT. Импортированный лог не подтверждает полноту всей истории и не устанавливает денежную стоимость.

## Пользовательский сценарий приёмки

Безопасный явно обозначенный synthetic JSONL + валидный/невалидный JSON-ответ + небольшой schema-2 metrics ledger → локальные команды сводки, проверки ответа и существующий planner → точные числа/явные unknown, отказ на неверном типе, `hold` при исчерпании бюджета → адресные tests, ручной CLI-сценарий, review и свежий acceptance gate. Граница доставки: local-verified; не live-pilot, не deployment и не доказательство экономии.

## Автономность и продолжение

- Источник текущего разрешения: отдельное подтверждение HRE-012 revision 1 и локального commit в текущем чате; повторного подтверждения на согласованные безопасные шаги не требуется.
- После явного подтверждения: выполнить оба среза, адресные тесты, необходимые исправления, два прохода review и configured gates без повторного «продолжай».
- Один source writer в текущем грязном checkout; primary ведёт только канонический журнал/паспорт и приёмку. Не создавать worktree и не откатывать существующие изменения.
- Максимум один активный помощник: Luna/xhigh на реализацию, затем Astra/xhigh на независимое read-only review. Это две последовательные роли, не параллельные записи. Primary model/effort сейчас не подтверждены; не выдумывать их в telemetry и не менять модель primary через план.
- Отдельное согласование: живой Codex/API-пилот, действительный процессный supervisor, новые полномочия/риск, распространение, публикация или изменение границ результата.

## Контракт и наблюдения до правки

- HEAD: `3584851049dae987ab040a34f2c5a717ff87a238`; branch: `codex/hre-004-update-watcher`. Существующие tracked/untracked изменения HRE-011 и пользовательский baseline сохраняются. Недоступный `tmpbceccdgc/` не трогать.
- Зафиксированные SHA-256: AGENTS.md `fe3da9b582312e1cdf63c4941ea7fbdb61da410fc9aede154b6394422d0cc8b7`; CONTEXT.md `9a621de1a3921d60e28277dfdbf0a77c98ffde7b96baa9ae6b94d93893158e9d`; harness-release.json `6639bab982c154838fe312f71bca78cdc6d00aac803d8040caa4898fa9fd5611`; local Goal Runner SKILL `d93c5909068a2deaf51e18b72c2910694b3a69f232072caec76cd75a471aeabc`.
- Graphify query `metrics context retry goal gate`, budget 1200: найдены metrics, acceptance и progress. Это навигация; граф отстаёт от HRE-011, чтение исходников имеет приоритет. Warning о версии skill не даёт полномочий на install/rebuild.
- Официальный источник прочитан 2026-10-03: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode). `--json` выдаёт события, `turn.completed.usage` содержит счётчики; `--output-schema` задаёт JSON Schema ответа. Это не доказательство работоспособности CLI на этом ПК и не подтверждение истинности ответа.
- Переиспользование: `harness_metrics.py` — validate/normalize/iter_records/task_summary и схема 2; `goal_orchestrator.py` — существующий read-only planner; `goal_progress.py` — имеющийся no-progress gate; acceptance — существующий gate. Не создавать второй ledger/DAG/guard для того же no-progress.
- Startup pointers: `harness_metrics.py` validate_event/normalize_event/task_summary; `goal_runner_validator.py` validate_passport; `goal_orchestrator.py` plan_actions; `goal_progress.py` check/record. Поиск в этих четырёх источниках достаточен для выбора границы; implementation packet получает только необходимые участки.
- Контекст проекта не считается актуальным разрешением на этот срез; HRE-011 завершён, его approval не переиспользуется.
- Гипотеза: строгий машинный контракт и наблюдаемые counters устранят класс ошибок типов/неизвестного usage; budget hold предотвратит разрешение очередной итерации сверх объявленного измеренного порога. Экономия времени/денег пока неизвестна.

### Исторический вопрос перед проекцией паспорта — закрыт до реализации

```json
{
  "schemaVersion": 1,
  "open_question": "Какие remaining validation rules нужны для честного planning passport без approval и без активных агентов?",
  "why": "Не выдумывать подтверждение и не допустить исполняемый план до ответа пользователя.",
  "known_gap": "Уже установлено, что approvedPassportRevision должен быть int >= 1 даже в planning; оставшиеся проверки chain/agent ещё не прочитаны адресно.",
  "reading_budget": {"startup_pointers_max": 5, "retrieval_rounds_max": 3, "additional_pointers_per_round_max": 2, "total_pointers_max": 6, "characters_per_round_max": 12000},
  "startup_pointers": [
    {"path": "goal_runner_validator.py", "line": 230, "symbol": "validate_passport", "reason": "Дочитать проверки неисполняемого chain и registry, не менять validator ради draft."}
  ],
  "sufficiency_test": "В draft нет ready/running/done, standing authority absent, approved revision null; validator сообщает только ожидаемое отсутствие approved revision."
}
```

## Контракт минимальной реализации

1. **Trace summary.** Явно выбранный файл внутри корня; только UTF-8 JSONL, <= 2 000 000 bytes, <= 10 000 событий, <= 64 000 bytes/строку. Не сканировать сессии/.codex и не печатать/сохранять command text, сообщения, prompts, raw tool output или секреты. Дубликаты JSON keys, отрицательные/bool counters, неоднозначная/повторная terminal usage и повреждённый trace отклонять; неизвестное не превращать в ноль. Первая версия — один turn на trace, multi-turn отклонять с явной причиной; повторный импорт не создаёт telemetry автоматически. Cached/reasoning counters не прибавлять повторно к input/output. Model/effort/duration/acceptance не выводить из слов модели; вне наблюдаемого trace они unknown. Для записи в существующий ledger primary использует проверенный checkpoint и существующий record contract.
2. **Typed result.** Один фиксированный небольшой JSON Schema: статус, evidence references, результаты проверок, unknown и stop reason. Локальный validator проверяет обязательные поля/типы/enum/limits и неизвестные поля; `false` не заменяется строкой. Ответ модели не исполняется, ссылки не открываются. Объявленный success без свежего локального acceptance не становится подтверждённым результатом; shape validation — отдельный результат, не acceptance. Схема пригодна для будущего `--output-schema`, но живой запуск не входит.
3. **Budget hold.** Opt-in budget в chain, не глобальный default. Порог относится только к учтённым run deltas: attempts, input+output tokens и суммарной observed duration. Before next launch planner читает лишь явно указанный schema-2 ledger текущего chain. При достижении/превышении любого порога, отсутствии/невалидности требуемой метрики, дубликате runId либо недоступном ledger — `hold` с машинной причиной; исходный бюджет/ledger не переписывать. Без budget сохранить текущие actions. История с неполным покрытием не означает фактический общий лимит; это pre-launch gate по записанным данным. Already-running agents не прерываются этим кодом. No-progress остаётся отдельным существующим контрактом.

## Карта воздействия и откат

- Новые границы недоверенного ввода: trace, JSON result, budget/metrics; reject traversal/reparse/secret paths до чтения, ограничивать bytes/counts, не показывать ошибочное содержимое в исключениях.
- Компоненты: новый небольшой stdlib helper, fixed schema, existing planner; consumers — только явные локальные CLI и опционально planner budget. Legacy passports/metrics/no-budget behavior сохраняются.
- Риск: medium, независимый safety/correctness review ввиду новых границ ввода. Нет сети, auth, миграций, новых пакетов и model calls.
- Первая достаточная ступень лестницы: reuse existing metrics/planner, затем stdlib для нового bounded parser/shape validation. Новый general-purpose JSON Schema framework, provider adapter и process supervisor не нужны.
- Разрешённые source paths: `harness_codex.py`, `tests/test_harness_codex.py`, `templates/codex-result.schema.json`, `goal_orchestrator.py`, `tests/test_goal_orchestrator.py`, `docs/CODEX_EXEC.md`. Primary отдельно владеет только новыми HRE-012 journal/passport/acceptance/runtime/metrics.
- Откат: точечно отменить только delta HRE-012 по записанному baseline, оставить HRE-011/пользовательские файлы; не reset/checkout/recursive delete. Budget opt-in можно не включать; legacy поведение тогда неизменно.

## Goal runner state

- Chain ID: HRE-012; project root: D:/6 Проекты/Харнес разработка; data owner: пользователь aidzm.
- Status: complete для implementation chain после source review/gates; final staged proofs и уже разрешённый local commit — отдельные handoff checkpoints. Plan revision: 1; Approved passport revision: 1; Approval provenance: `019fca39-7a3e-7a90-a726-a47e3c72dc19`, сообщение «коммит и Подтверждаю HRE-012 revision 1».
- Primary/current agent task ID: /root; app chat UUID подтверждён native Goal tool: `019fca39-7a3e-7a90-a726-a47e3c72dc19`. Native Goal закрывается только после фактической проверки разрешённого local commit, не по одному scheduling signal паспорта.
- Delivery boundary: local-verified; external-side-effect boundary: no network/model calls/external writes.
- Checkout/worktree policy: current shared dirty checkout, one source writer; `shared-checkout` в projection — только identity label этого физического корня, не отдельный worktree.
- Commit policy: primary-only, восемь точных HRE-012 paths, без push; hash коммита и post-commit status фиксируются в ignored runtime receipt, а не самоссылкой в исходнике. До commit проверить staged scope и сохранение baseline; clean HEAD compatibility уже доказана.
- Current verified boundary: G02 — source independently accepted, configured gates и clean-HEAD compatibility PASS. G00 — skipped administrative bootstrap без child run; implementation/review G01/G02 и полный знаменатель 4 критерия не изменились. Новая делегация не требуется.
- Executable plan snapshot: `.harness/work/hre-012.passport.json`; approved revision связан с настоящим подтверждением, validate перед каждым worker write/registry change.
- Baseline ID: hre012-existing-v1; treatment ID: hre012-trace-contract-v1. Это design IDs; сопоставимые live runs пока не выполняются.
- Metrics: `.harness/metrics/hre-012.jsonl`, schema 2; append-only checkpoints и наблюдавшиеся failures сохранены. Per-run input/output tokens unknown/null, synthetic CLI counters не импортированы как live usage. Duration относится к наблюдавшимся checkpoint windows/command execution, не к provider latency; сравнения стоимости и скорости с baseline нет. Fresh task progress берётся только из acceptance C01–C04.
- Global agent cap: 1; HRE-012 agents `/root/hre012_g01` (GPT-6 Luna/xhigh) и `/root/hre012_g02` (GPT-6 Astra/xhigh) done, active children 0. Roles работали последовательно; Child quota 0. Delegation depth cap: 1; no separate tasks/successors; standing authorization approved только bounded continuation текущего паспорта; archive only explicit command.

## Минимальные срезы и приёмка

| ID | Результат | Зависимость | Исполнитель | Приёмка |
| --- | --- | --- | --- | --- |
| G01 | Trace summary + typed result + opt-in budget hold | none | один Luna/xhigh worker | C01–C03 target tests + CLI examples |
| G02 | Проверенная совместимость, безопасность, simplify и интеграция | G01 | Astra/xhigh read-only review; primary gates/acceptance | C04 + fresh C01–C03 |

Полный знаменатель до реализации: **4 критерия**, не сокращать его после ошибки.

- C01 trace: точные счётчики official-shaped fixture; неизвестные поля/повреждение/лимиты/повтор terminal/multi-turn; нет raw content в отчёте; никакой автоматической записи ложной acceptance.
- C02 response: валидный пример проходит, строка вместо bool/лишние ключи/плохой status/небезопасные ссылки отвергаются; success declaration не выдаёт acceptance.
- C03 budget: below/exact/over limits; unknown/invalid/duplicate/foreign-chain/legacy telemetry; no-budget unchanged; исходные файлы/бюджет не меняются; running action и no-progress semantics не подменяются.
- C04 integration: независимое correctness/security review, отдельный simplify pass, ручной локальный CLI-сценарий, configured prechange/postchange/release gates, baseline hashes сохранены, свежие C01–C03 и нет запрещённых side effects. Synthetic fixtures не объявлять реальным пилотом или измеренной экономией.

## Журнал проверок

- Orientation: git status/HEAD/четыре baseline hashes сверены; HRE-012 files ещё не существовали; Graphify read-only navigation выполнена; official documentation открыта.
- 2026-10-03 execution: configured `prechange` PASS, exit 0; существующая грязная копия — ожидаемое предупреждение, owned source paths не пересекают dirty baseline. Test count/duration не перепечатываются из памяти: полный лог был усечён tool output. Для следующих gates использовать bounded summary capture с фактическими count/duration. Временный PSModulePath только для процесса содержит стандартные Windows PowerShell modules; системные настройки не менялись. Gate запущен через обычное разрешение для локальных temporary-directory tests, не обход прав.
- Commit compatibility: в `HEAD:harness_metrics.py` уже существуют validate_record, iter_records и task_summary/schema 2; не импортировать незакоммиченный harness_instruction_audit.py. Для scoped commit выполнить проверки чистой копии HEAD + exact HRE-012 paths; остальные dirty baseline files не переносить в commit.
- Подготовлена ignored verification copy `.harness/runtime/hre012-clean-copy` из `git archive HEAD` (108 tracked paths), без `.git`, новых tasks или регистрации worktree; известные sensitive-name tracked paths перед копированием отсутствовали. Ни source checkout, ни baseline не изменены. Active non-sample Git hooks отсутствуют, commit identity настроена (значения не печатались). Эта копия будет проверяться только после переноса точного HRE-012 delta и служить clean integration view для primary commit через временный `--work-tree` аргумент, без изменения Git config.
- G01 acknowledgement соответствует исходу, шести owned paths, запретам и C01–C03; ambiguity отсутствует. Parent отдельно уточнил hard byte bounds вместо unbounded read и confirmed project-root binding для budget ledger. По лестнице — reuse существующих helpers/metrics/planner, затем минимальный stdlib parser; не брать uncommitted audit/evaluation helpers.
- C04 до любых execution proofs уточнён: criterion подтверждает review/gates/совместимость и readiness exact scoped commit; сам разрешённый commit — последующий checkpoint передачи. Это устраняет круг «acceptance требует commit, но commit разрешён только после acceptance»; 4 критерия/исходы/порог не сокращены, failed evidence не было и не удалялось.
- До первого acceptance execution исправлена форма oracle C01–C03: gate сравнивает `expect` с целой строкой, не substring. Команды и четыре критерия сохранены; вместо короткого имени используется полная успешная строка unittest `METHOD (test_harness_codex.CLASS.METHOD) ... ok`, проверенная локальным TestLoader без выполнения тестов. Нулевой discovery либо иной вывод не удовлетворит marker. Это исправление oracle, не снижение порога; предыдущих execution proofs нет.
- CLI trace `.harness/runtime/hre012-cli-trace.jsonl` — явно synthetic official-shaped input с canary текстом; ожидается 100 input + 30 output = 130, не 230 и не 150. Не импортировать synthetic counts как usage реальной задачи; raw canary не должен появиться в выводе.
- Retrieval round 1: дочитаны строки 231–375 существующего validator, без новых source pointers, в пределах 12 000 символов. Для planning allowed `currentVerifiedSubgoal: null` и registry без активных агентов; approval не требуется подменять.
- Draft validator выполнен: единственный ожидаемый `FAIL CHAIN_REVISION` из-за `approvedPassportRevision: null`. Это преднамеренно неисполняемый draft, не дефект реализации и не failed attempt; после approval заполнить настоящий provenance/revision и получить PASS до dispatch.
- Read-only task report выполнен: telemetryStatus unavailable, runs 0, tokens/failedAttempts/progress null, basis acceptance-unavailable. Критерии C01–C04 пока не материализованы в gate и не пройдены; 0/4 или 100% не заявлять.
- После approval сначала target tests, затем configured gates без дублирования полного suite в одном состоянии. Не повторять diagnostic attempt более двух независимых стратегий без локализованной причины.
- Контроль изменений scope: материализованный process supervisor/живой пилот требуют нового явного согласования, не добавлять их под видом окончания G01.

## Передача

- G01 передан и source writer остановлен. Изменены пять из шести назначенных путей; существующий `tests/test_goal_orchestrator.py` семантически сохранён. Primary targeted: 37/37 PASS, unittest duration 0.822 s. Reuse rung 2: existing metrics/planner/path guards + minimal stdlib decoder; новых dependencies и supervisor нет.
- Worker observed verification: 5 unittest invocations, 3 nonzero. Первый failed suite включал WinError 5 среды и parity mismatch; ещё два failed pure runs — parity и ошибочный depth fixture. Исправлены локализованные schema/test несовпадения; финальный pure run 4/4 PASS. Файловый suite повторён primary с обычным reviewed разрешением и прошёл; ACL/TEMP/system settings не менялись. Это не 0 failed attempts.
- Primary synthetic CLI: все 6 сценариев PASS. Trace: 100 input + 30 output = 130, cached 80/reasoning 20 не прибавлены; canary отсутствует. Valid result: shapeValid true/acceptance not_checked; строка вместо bool: safe result_checks_invalid, explicit exit 2. Planner: below → launch, exact token limit → budget_max_tokens_reached, null token coverage → budget_unknown_tokens. Это только planning output, не реальный launch.
- Два primary verification-wrapper промаха не скрыты: первая baseline команда прочитала wrapper JSON вместо protectedBaseline и была отвергнута; исправленная строгая проверка подтвердила 20/20 неизменных SHA256. В первом CLI assertion PowerShell передал nonzero как exit 1; явное `exit $LASTEXITCODE` подтвердило настоящий Python exit 2. Новых дефектов Harness этими промахами не установлено.

- Configured root postchange до G02 findings: 220 tests PASS / 18.703 s, gate PASS / 26 519 ms. Отрицательные fixture сообщения внутри успешного suite не считаются failed verification invocations. Этот gate не переносится на будущие source fixes.
- G02 first correctness pass отклонил срез до final acceptance: P1 duplicate passport budget key позволяет заменить maxTokens 15 на 1000 и получить launch; P1 Windows trailing-space/dot aliases обходят secret-path lexical check; P2 JSON Schema `$` допускает конечный newline вопреки runtime fullmatch; P2 сумма двух допустимых 4300-digit counters приводит к небезопасной ошибке сериализации. Реальные секреты не читались. Findings воспроизведены независимо; это pre-acceptance defects, не escaped production incidents.
- G02 отдельный simplify: reuse + stdlib остаются достаточными, новых dependencies/абстракций не нужно. 25 pure tests PASS / 0.017 s + 17 budget probes PASS; 3 verification invocations, 0 nonzero. Green probe process не превращает найденные дефекты в acceptance. G01 вновь открыт, verified boundary возвращён к G00; исправить четыре конкретные границы одной bounded correction, затем повторить независимое review.

- G01 bounded correction: strict passport decoder reused without changing Path.read_text consumers; Windows trailing dot/space component rejection before secret checks; absolute schema end anchors and behavioral newline tests; counters and sum bounded to 4 300 decimal digits with safe usage_total_over_limit. Five source paths corrected, existing orchestrator tests unchanged. Worker pure: 9 tests PASS / 445 ms, 0 failed invocations. Primary target: 44/44 PASS / 0.673 s, including the four defect regressions and preserved old planner scenarios. Source writer stopped; independent G02 re-review still required.

- G02 re-review: strict duplicate parsing, 8 alias cases и 13 actual Draft202012Validator parity probes подтверждены. 28 pure tests PASS / 0.016 s; 1 verification invocation, 0 nonzero. Остался локализованный P2: при process-local int_max_str_digits=640 сумма двух допустимых 640-digit integers имеет 641 цифру и json.dumps вне try выбрасывает ValueError. Изменения лимита проверялись в отдельном процессе с finally restoration, не глобально. Исправить существующий CLI-handler, не вводить numeric framework; сохранить safe reason/exit 2 и добавить эту регрессию. C04 не принят.

- Final microfix: output serialization moved inside the existing CLI handler, CodexInputError codes preserved; ValueError → constant output_serialization_failed/exit 2, no raw exception. Pure regression restores process-local 640 limit in finally: 1/1 PASS / 0.004 s, 1 invocation / 0 nonzero. Primary final target: 45/45 PASS / 0.513 s.
- Final independent G02 source review принят: end-to-end 640-digit sum returns safe reason/exit 2 with empty stdout, all four earlier defect boundaries reconfirmed. 1 regression PASS / 0.003 s + 18 bounded probes PASS; 1 invocation / 0 nonzero. Separate simplify accepted reuse of existing handler, no dependencies/abstractions added. Это source acceptance, не утверждение release/commit или 4/4 ledger.

- Final original postchange: 228 tests PASS / 19.411 s; configured gate PASS / 27 053 ms. Clean HEAD 3584851 + exact eight HRE-012 paths: 191 tests PASS / 19.620 s; configured release gate PASS / 40 463 ms, including isolated installer fixtures only in GUID temp test profile. Lower clean count is expected: uncommitted HRE-011 modules/tests are excluded. This demonstrates no dependency on their dirty implementation.
- Clean view has no .git; expected diff-scope warning is covered by manual eight-path copy hashes plus primary staged-scope review. Configured release PASS is local validation, not published payload, real installation or distribution to projects/PCs; AGENTS/CONTEXT/release manifest and all 20 protected baseline hashes remain outside this commit.

- Final staged-scope audit: exactly eight approved files; no protected baseline path staged. It caught one extra empty EOF line in the new test file. With both source owners done, primary integration removed only that empty line; AST equivalence against the already-tested clean copy is checked before recopy. No behavior or test cases changed; the source gates above are retained with this explicit nonsemantic formatting note, while final C01–C03 and manual C04 are refreshed to the final index. No new delegation/feature scope.

Source outcome, independent review and configured gates verified. Final staged C01–C04 must be refreshed to the exact index before ordinary primary-only local commit; actual commit hash/post-commit check go in ignored runtime receipt. Native Goal completes only after that checkpoint. Real usage, economic benefit, live Codex/--output-schema pilot and global adoption remain unverified; push is not performed.
